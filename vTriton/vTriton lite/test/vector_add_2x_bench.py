"""vector_add 2x variant for counterfactual (US-SB-006).

Same as vector_add_bench.py but with N=32M (2x the data). Used for the
work-scaling counterfactual experiment: profile both N=16M and N=32M,
verify the model predicts the scaling correctly.
"""
import os
import torch
import torch.nn as nn
import triton
import triton.language as tl


@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n_elements, BLOCK: tl.constexpr):
    pid = tl.program_id(axis=0)
    offsets = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offsets < n_elements
    x = tl.load(x_ptr + offsets, mask=mask, other=0.0)
    y = tl.load(y_ptr + offsets, mask=mask, other=0.0)
    tl.store(out_ptr + offsets, x + y, mask=mask)


N_ELEMENTS = 32 * 1024 * 1024  # 32 M (2x the baseline)
BLOCK = 2048


def build_inputs():
    device = "npu"
    torch.manual_seed(0)
    x = torch.randn(N_ELEMENTS, device=device, dtype=torch.float32)
    y = torch.randn(N_ELEMENTS, device=device, dtype=torch.float32)
    out = torch.empty_like(x)
    return {"x": x, "y": y, "out": out}


class Model(nn.Module):
    def forward(self, data):
        x, y, out = data["x"], data["y"], data["out"]
        grid = (triton.cdiv(N_ELEMENTS, BLOCK),)
        add_kernel[grid](x, y, out, N_ELEMENTS, BLOCK=BLOCK)
        return (out,)


def reference(x, y):
    """CPU reference for correctness checks."""
    return x + y


if __name__ == "__main__":
    data = build_inputs()
    out = Model().forward(data)[0]
    print("vector_add_2x launch OK", out.shape, out.dtype)
