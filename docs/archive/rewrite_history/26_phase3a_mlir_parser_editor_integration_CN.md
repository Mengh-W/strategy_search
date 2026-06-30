# Phase 3A: MLIR/HIVM 真实解析器 + HivmOpsEditor 集成

> 版本: v3.3.2 → Phase 3A  
> 日期: 2026-06-27  
> 状态: 已完成  
> 依赖: 纯 Python，无外部依赖

---

## 1. 概述

将 v3.3.2 中 `structural_rewrite.py` 的**文本级正则替换**升级为**真实 MLIR/HIVM 解析器 + HivmOpsEditor** 操作级编辑。

### 1.1 核心变更

```
Before (Phase 2H):                    After (Phase 3A):
┌──────────────────────┐               ┌──────────────────────┐
│ structural_rewrite.py │               │ structural_rewrite.py │
│  text-based regex     │               │  apply_structural_    │
│  _apply_*_via_text    │               │  rewrite()            │
│                       │               │    │                  │
│  count_structural_ops │               │    ├─ _HAS_REAL_      │
│  (regex-based)        │               │    │  PARSER? ───YES──┤
└──────────────────────┘               │    │                  │
                                       │    │    ┌─────────────┤
                                       │    │    │ Editor-     │
                                       │    │    │ based path  │
                                       │    │    │ (production)│
                                       │    │    └─────────────┤
                                       │    │                  │
                                       │    └─ NO ── text-based│
                                       │           fallback     │
                                       └──────────────────────┘
                                                │
                           ┌────────────────────┼────────────────────┐
                           │                    │                    │
                    ┌──────▼──────┐    ┌───────▼───────┐    ┌───────▼──────┐
                    │ hivm_parser │    │ hivm_ops_editor│    │ hivm_backend │
                    │ (tokenizer, │    │ (CRUD, walk,   │    │ (auto-detect,│
                    │  IR tree,   │    │  barrier,      │    │  C++/Python  │
                    │  serializer)│    │  hoist, sync)  │    │  bridge)     │
                    └─────────────┘    └───────────────┘    └──────────────┘
```

### 1.2 设计原则

- **自动降级**: 当真实解析器可用时使用 editor-based 路径，不可用时回退到文本级正则替换
- **往返保真度**: 未修改的操作保留原始文本 (`raw_text`)，仅修改/新建的操作从结构化字段生成文本
- **审计追踪**: 每次编辑记录 `before`/`after` 操作级详情，标记 `editor_based: True`
- **零外部依赖**: 全部纯 Python 实现，无需 LLVM/MLIR 构建

---

## 2. 修改的文件

### 2.1 `strategy_search/structural_rewrite.py`

**新增导入** (第 39-52 行):

```python
# Real MLIR/HIVM parser + HivmOpsEditor (Phase-3A integration)
try:
    from .hivm_parser import (
        MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
        parse_hivm_file, parse_hivm_text, serialize_module, write_module,
    )
    from .hivm_ops_editor import (
        HivmOpsEditor, HivmOpInfo,
        PipeAttr, EventAttr,
        HIVM_SYNC_OPS, HIVM_DMA_OPS,
    )
    _HAS_REAL_PARSER = True
except ImportError:
    _HAS_REAL_PARSER = False
```

**重构 `apply_structural_rewrite`** (第 386-395 行):

```python
def apply_structural_rewrite(ir_text, strategy, safety="balanced"):
    if _HAS_REAL_PARSER:
        return _apply_structural_rewrite_via_editor(ir_text, strategy, safety)
    return _apply_structural_rewrite_via_text(ir_text, strategy, safety)
```

**新增函数列表**:

| 函数 | 行号 | 功能 |
|------|------|------|
| `_apply_structural_rewrite_via_editor` | 421 | Editor-based 重写主入口 |
| `_editor_replace_barrier_all` | 469 | Barrier → set_flag/wait_flag |
| `_editor_insert_sync_before_vector` | 514 | CV 边界同步插入 |
| `_editor_hoist_invariant_q_load` | 577 | Q Load 循环提升 |
| `_editor_remove_adjacent_duplicate_sync` | 642 | 相邻重复同步删除 |
| `_editor_remove_redundant_gm_roundtrip` | 678 | GM 往返检测 (延迟到 Phase 3C) |
| `_count_structural_ops_via_editor` | 775 | Editor-based 操作计数 |
| `_count_structural_ops_via_regex` | 769 | Regex 操作计数 (回退) |

**重构 `count_structural_ops`** (第 758-766 行):

```python
def count_structural_ops(ir_text):
    if _HAS_REAL_PARSER:
        return _count_structural_ops_via_editor(ir_text)
    return _count_structural_ops_via_regex(ir_text)
```

### 2.2 `strategy_search/__init__.py`

**新增导出** (第 24-42 行):

```python
# Phase-3A: Real MLIR/HIVM parser + HivmOpsEditor integration
from .hivm_parser import (
    MLIRModule, MLIRFunction, MLIRRegion, MLIRBlock, MLIROperation,
    SSAValue, MLIRAttribute,
    parse_hivm_file, parse_hivm_text, serialize_module, write_module,
    MLIRParseError, MLIRParser, MLIRSerializer, MLIRTokenizer,
)
from .hivm_ops_editor import (
    HivmOpsEditor, HivmOpInfo,
    AddressSpace, PipeAttr, EventAttr,
    HIVM_DMA_OPS, HIVM_VECTOR_UNARY_OPS, HIVM_VECTOR_BINARY_OPS,
    HIVM_VECTOR_SPECIAL_OPS, HIVM_MACRO_OPS, HIVM_SYNC_OPS, HIVM_ALL_OPS,
    load_editor, create_editor_from_text,
)
from .hivm_backend import (
    HivmBackend, BackendKind, BackendCapabilities,
    get_backend, reset_backend, force_python_backend,
)
```

### 2.3 `_test_structural_rewrite_integration.py` (新建)

8 个集成测试覆盖全部编辑类型：

| 测试 | 内容 |
|------|------|
| Test 1 | Parse + Editor 集成 |
| Test 2 | Barrier → directional sync (editor) |
| Test 3 | `apply_structural_rewrite` (barrier) |
| Test 4 | `apply_structural_rewrite` (CV sync) |
| Test 5 | `apply_structural_rewrite` (Q load hoist) |
| Test 6 | `count_structural_ops` (editor-based) |
| Test 7 | Full pipeline 含验证 |
| Test 8 | HivmBackend 集成 |

---

## 3. 未修改的现有文件

以下文件已在之前版本中存在，本次集成**未修改**：

| 文件 | 说明 |
|------|------|
| `strategy_search/hivm_parser.py` | 真实 MLIR/HIVM 解析器 (tokenizer, IR tree, serializer) |
| `strategy_search/hivm_ops_editor.py` | HivmOpsEditor CRUD API (Python-native) |
| `strategy_search/hivm_backend.py` | 统一后端桥接 (auto-detect C++/Python) |
| `_test_editor_integration.py` | 已有测试 (parse → edit → serialize → re-parse) |
| `_test_roundtrip.py` | 已有测试 (往返保真度) |
| `_test_real_parser.py` | 已有测试 (解析器验证) |

---

## 4. 5 种 Editor-Based 编辑操作

### 4.1 Barrier → Directional Sync

```python
# 替换 hivm.hir.barrier {mode = "ALL"} 为 set_flag/wait_flag 对
editor.barrier_to_directional_sync(
    barrier_op,
    set_pipe=PipeAttr.PIPE_MTE2,
    wait_pipe=PipeAttr.PIPE_M,
    event_id=EventAttr.EVENT_ID0,
)
```

**验证结果**: `fa_bad_inefficient.hivm.mlir` 中 2 个 barrier → 0, 新增 3 set_flag + 3 wait_flag

### 4.2 CV 边界同步插入

```python
# 在 Cube/Fixpipe 和第一个 Vector 操作间插入同步边界
editor.insert_cv_pipeline_sync(
    cube_op, vector_op,
    set_pipe=PipeAttr.PIPE_FIX,
    wait_pipe=PipeAttr.PIPE_V,
    event_id=EventAttr.EVENT_ID1,
)
```

### 4.3 Q Load 循环提升

```python
# 将 Q_gm load + nd2nz 从 scf.for 循环中提升到循环前
editor.hoist_q_load(load_op, nd2nz_op)
```

**安全门**:
1. 检查 hoisted 操作不引用循环归纳变量
2. 仅作用于 `Q_gm` → `q_ub` → `q_l1` 模式

### 4.4 相邻重复同步删除

```python
# 删除相邻重复的 set_flag/wait_flag 对
editor.delete_op(duplicate_op)
```

### 4.5 GM 往返删除 (延迟)

```python
# 候选检测但不执行删除，延迟到 Phase 3C
# 需要 alias/dependency proof
```

---

## 5. 测试结果

### 5.1 集成测试 (`_test_structural_rewrite_integration.py`)

```
Test 1: Parse + Editor integration ........... PASS
Test 2: Barrier → directional sync ........... PASS
Test 3: structural_rewrite (barrier) ......... PASS
Test 4: structural_rewrite (CV sync) ......... PASS
Test 5: structural_rewrite (Q load hoist) .... PASS
Test 6: count_structural_ops (editor-based) .. PASS
Test 7: Full pipeline with validation ........ PASS
Test 8: HivmBackend integration .............. PASS

ALL INTEGRATION TESTS PASSED
```

### 5.2 回归测试

| 测试文件 | 结果 |
|----------|------|
| `_test_editor_integration.py` | PASS |
| `_test_roundtrip.py` | PASS (往返保真度 100%) |
| `_test_real_parser.py` | PASS |

### 5.3 往返保真度验证

- `fa_best.hivm.mlir`: 40 lines original, 40 lines serialized — **100% match**
- `fa_bad_inefficient.hivm.mlir`: 43 lines original, 43 lines serialized — **100% match**

### 5.4 编辑操作验证 (fa_bad_inefficient.hivm.mlir)

| 指标 | Before | After | Delta |
|------|--------|-------|-------|
| barrier_all | 2 | 0 | **-2** |
| set_flag | 0 | 3 | **+3** |
| wait_flag | 0 | 3 | **+3** |
| load | 3 | 3 | 0 |
| cube | 2 | 2 | 0 |
| vector | 5 | 5 | 0 |

---

## 6. 架构兼容性

### 6.1 自动降级路径

```
apply_structural_rewrite()
    │
    ├─ _HAS_REAL_PARSER == True
    │   └─ _apply_structural_rewrite_via_editor()
    │       ├─ parse_hivm_text() → MLIRModule
    │       ├─ HivmOpsEditor(module)
    │       └─ editor.export_to_string()
    │
    └─ _HAS_REAL_PARSER == False
        └─ _apply_structural_rewrite_via_text()  (legacy)
            └─ text-level regex replacement
```

### 6.2 后端优先级

```
HivmBackend.detect()
    ├─ 1. C++ hivm-operation-backend (real MLIR, highest priority)
    ├─ 2. C++ hivm-strategy-rewrite (text bridge)
    └─ 3. Python HivmOpsEditor (fallback, always available)
```

### 6.3 向后兼容

- 所有现有 `structural_rewrite.py` 的公共 API 保持不变
- `count_structural_ops()` 返回相同 key 集合
- `StructuralRewriteResult` 数据结构不变
- 新增 `editor_based: True` 标记用于审计追踪

---

## 7. 下一步

| Phase | 任务 | 状态 |
|-------|------|------|
| 3A | 真实解析器 + HivmOpsEditor 集成 | **已完成** |
| 3B | 依赖图与事件活跃性分析 | 待实施 |
| 3C | 缓冲活跃性与别名检查 | 待实施 |
| 3D | 安全 GM 往返删除 | 待实施 |
| 3E | tritonsim-hivm DES/trace 验证 | 待实施 |