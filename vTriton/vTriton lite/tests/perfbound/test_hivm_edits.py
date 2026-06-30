# Tests for HIVM edit primitives (A.6.2)
#
# Each edit must provably change the targeted structural field.
# No-op / malformed inputs must raise.

import json
import pytest
from pathlib import Path

from perfbound.validate.hivm_edits import (
    raise_repeat,
    insert_pingpong,
    merge_transfers,
    verify_edit_via_extract,
    HivmEdit,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_HIVM = FIXTURE_DIR / "sample_hivm.json"


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _write_tmp(ops: list[dict]) -> Path:
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"operations": ops}, f)
        return Path(f.name)


class TestRaiseRepeat:
    """raise_repeat must multiply the repeat field on compute ops."""

    def test_changes_repeat_on_cube_ops(self):
        edited = raise_repeat(SAMPLE_HIVM, factor=2)
        data = _load_json(edited)
        cube_ops = [op for op in data["operations"] if op["pipe"] == "Cube"]
        assert len(cube_ops) > 0
        for op in cube_ops:
            assert op["repeat"] == 2, f"repeat should be 2, got {op['repeat']}"

    def test_preserves_original(self):
        original = _load_json(SAMPLE_HIVM)
        _ = raise_repeat(SAMPLE_HIVM, factor=3)
        after = _load_json(SAMPLE_HIVM)
        assert original == after, "original file should not be modified"

    def test_mte_ops_unchanged(self):
        edited = raise_repeat(SAMPLE_HIVM, factor=4)
        data = _load_json(edited)
        mte_ops = [op for op in data["operations"] if op["pipe"] != "Cube"]
        for op in mte_ops:
            # MTE ops should not have repeat changed
            assert op.get("repeat", 1) == 1

    def test_factor_1_is_noop_on_repeat_value(self):
        edited = raise_repeat(SAMPLE_HIVM, factor=1)
        data = _load_json(edited)
        cube_ops = [op for op in data["operations"] if op["pipe"] == "Cube"]
        for op in cube_ops:
            assert op["repeat"] == 1  # 1 * 1 = 1

    def test_invalid_factor_raises(self):
        with pytest.raises(ValueError, match="factor must be >= 1"):
            raise_repeat(SAMPLE_HIVM, factor=0)

    def test_malformed_input_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"nodes": []}, f)
            bad_path = Path(f.name)
        with pytest.raises(ValueError, match="operations"):
            raise_repeat(bad_path)
        bad_path.unlink()


class TestInsertPingpong:
    """insert_pingpong must add duplicate buffer ops after MTE_UB transfers."""

    def test_adds_ops(self):
        original = _load_json(SAMPLE_HIVM)
        orig_count = len(original["operations"])
        edited = insert_pingpong(SAMPLE_HIVM)
        data = _load_json(edited)
        # One MTE_UB op in fixture → one duplicate added
        assert len(data["operations"]) == orig_count + 1

    def test_duplicate_has_pingpong_suffix(self):
        edited = insert_pingpong(SAMPLE_HIVM)
        data = _load_json(edited)
        pingpong_ops = [op for op in data["operations"] if "pingpong" in op["name"]]
        assert len(pingpong_ops) == 1
        assert pingpong_ops[0]["name"] == "store_out_pingpong"

    def test_duplicate_has_unique_id(self):
        original = _load_json(SAMPLE_HIVM)
        max_orig_id = max(op["id"] for op in original["operations"])
        edited = insert_pingpong(SAMPLE_HIVM)
        data = _load_json(edited)
        pingpong_ops = [op for op in data["operations"] if "pingpong" in op["name"]]
        assert pingpong_ops[0]["id"] > max_orig_id

    def test_preserves_original(self):
        original = _load_json(SAMPLE_HIVM)
        _ = insert_pingpong(SAMPLE_HIVM)
        after = _load_json(SAMPLE_HIVM)
        assert original == after


class TestMergeTransfers:
    """merge_transfers must merge consecutive same-space MTE_GM transfers."""

    def test_reduces_op_count(self):
        original = _load_json(SAMPLE_HIVM)
        orig_count = len(original["operations"])
        edited = merge_transfers(SAMPLE_HIVM)
        data = _load_json(edited)
        # Fixture has two consecutive MTE2 ops (load_B at idx 1, load_B2 at idx 4)
        # They are NOT consecutive (matmul between them), so count stays same
        assert len(data["operations"]) == orig_count

    def test_merges_consecutive_same_space(self):
        import tempfile

        # Create fixture with consecutive same-space MTE2 ops
        ops = {
            "operations": [
                {"id": 1, "name": "load_a", "pipe": "MTE2", "bytes": 1024,
                 "src_space": "gm", "dst_space": "l0a"},
                {"id": 2, "name": "load_b", "pipe": "MTE2", "bytes": 2048,
                 "src_space": "gm", "dst_space": "l0a"},
                {"id": 3, "name": "matmul", "pipe": "Cube"},
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(ops, f)
            path = Path(f.name)

        edited = merge_transfers(path)
        data = _load_json(edited)
        assert len(data["operations"]) == 2  # merged to 1 MTE2 + 1 Cube

        mte_ops = [op for op in data["operations"] if op["pipe"] == "MTE2"]
        assert len(mte_ops) == 1
        assert mte_ops[0]["bytes"] == 1024 + 2048  # bytes summed
        path.unlink()

    def test_preserves_original(self):
        original = _load_json(SAMPLE_HIVM)
        _ = merge_transfers(SAMPLE_HIVM)
        after = _load_json(SAMPLE_HIVM)
        assert original == after

    def test_malformed_input_raises(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"bad_key": []}, f)
            bad_path = Path(f.name)
        with pytest.raises(ValueError, match="operations"):
            merge_transfers(bad_path)
        bad_path.unlink()


class TestNoOpGuards:
    """Edits that target zero ops must fail loudly (no-op guard)."""

    def test_raise_repeat_no_compute_ops_raises(self):
        # Only MTE ops, no Cube/Vector/Scalar → nothing to edit.
        path = _write_tmp([
            {"id": 1, "name": "load", "pipe": "MTE2"},
            {"id": 2, "name": "store", "pipe": "MTE3"},
        ])
        with pytest.raises(ValueError, match="no-op"):
            raise_repeat(path, factor=2)
        path.unlink()

    def test_insert_pingpong_no_mte_ub_raises(self):
        # No MTE_UB transfer present → nothing to double-buffer.
        path = _write_tmp([
            {"id": 1, "name": "load", "pipe": "MTE2"},
            {"id": 2, "name": "mm", "pipe": "Cube"},
        ])
        with pytest.raises(ValueError, match="no-op"):
            insert_pingpong(path)
        path.unlink()

    def test_merge_transfers_no_mte_gm_raises(self):
        # No MTE_GM ops at all → edit inapplicable.
        path = _write_tmp([
            {"id": 1, "name": "mm", "pipe": "Cube"},
            {"id": 2, "name": "act", "pipe": "Vector"},
        ])
        with pytest.raises(ValueError, match="no-op"):
            merge_transfers(path)
        path.unlink()

    def test_merge_transfers_nonconsecutive_does_not_raise(self):
        # MTE_GM ops present but not mergeable → legitimate no-merge, no raise.
        edited = merge_transfers(SAMPLE_HIVM)
        data = _load_json(edited)
        assert len(data["operations"]) == len(_load_json(SAMPLE_HIVM)["operations"])


class TestVerifyEditViaExtract:
    """Reversibility check: edits must be visible through the real extractor."""

    def test_raise_repeat_visible(self):
        edited = raise_repeat(SAMPLE_HIVM, factor=2)
        assert verify_edit_via_extract(SAMPLE_HIVM, edited) is True

    def test_factor_1_not_visible(self):
        # A genuine no-op edit is correctly reported as not visible.
        edited = raise_repeat(SAMPLE_HIVM, factor=1)
        assert verify_edit_via_extract(SAMPLE_HIVM, edited) is False

    def test_insert_pingpong_visible(self):
        edited = insert_pingpong(SAMPLE_HIVM)
        assert verify_edit_via_extract(SAMPLE_HIVM, edited) is True

    def test_merge_transfers_visible(self):
        path = _write_tmp([
            {"id": 1, "name": "load_a", "pipe": "MTE2", "bytes": 1024,
             "src_space": "gm", "dst_space": "l0a"},
            {"id": 2, "name": "load_b", "pipe": "MTE2", "bytes": 2048,
             "src_space": "gm", "dst_space": "l0a"},
            {"id": 3, "name": "mm", "pipe": "Cube"},
        ])
        edited = merge_transfers(path)
        assert verify_edit_via_extract(path, edited) is True  # op count dropped
        path.unlink()


class TestHivmEditDataclass:
    """HivmEdit dataclass carries gap metadata + apply callable."""

    def test_hivm_edit_callable(self):
        edit = HivmEdit(
            gap_name="gap4_intra_unit_exec",
            description="Raise repeat to amortize loop overhead",
            apply=lambda p: raise_repeat(p, factor=4),
        )
        assert edit.gap_name == "gap4_intra_unit_exec"
        result_path = edit.apply(SAMPLE_HIVM)
        data = _load_json(result_path)
        cube_ops = [op for op in data["operations"] if op["pipe"] == "Cube"]
        assert all(op["repeat"] == 4 for op in cube_ops)
