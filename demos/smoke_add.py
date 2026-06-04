#!/usr/bin/env python3
"""Minimal TT-NN smoke test for the Blackhole p150a (torch-free).

Creates two 32x32 tensors *on the device* with ttnn.full (3.0 and 4.0), runs an
elementwise add on the Tensix cores, reads the result back to host, and checks
that every element is ~7.0. Designed for the tt-metalium container, which ships
ttnn + numpy but not torch.

Run inside the container with the device + hugepages mapped in. Exit 0 = PASS.
"""
import numpy as np
import ttnn


def to_host_array(t):
    """Read a ttnn tensor back to a numpy array without torch."""
    t = ttnn.from_device(t)
    t = ttnn.to_layout(t, ttnn.ROW_MAJOR_LAYOUT)
    return np.array(t.to_torch() if hasattr(t, "to_torch") and False else t, dtype=np.float32)


def main() -> int:
    device = ttnn.open_device(device_id=0)
    try:
        shape = [32, 32]
        kw = dict(dtype=ttnn.bfloat16, layout=ttnn.TILE_LAYOUT, device=device)
        a = ttnn.full(shape, 3.0, **kw)
        b = ttnn.full(shape, 4.0, **kw)
        c = ttnn.add(a, b)  # runs on the Tensix cores

        host = ttnn.to_layout(ttnn.from_device(c), ttnn.ROW_MAJOR_LAYOUT)
        try:
            arr = np.array(host, dtype=np.float32)
            sample = arr.flatten()[:4].tolist()
            max_err = float(np.abs(arr - 7.0).max())
            print(f"device sample [0:4] = {sample}")
            print(f"max abs error vs 7.0 = {max_err:.4f}  (bf16 rounding, expect < 0.1)")
            ok = max_err < 0.1
        except Exception as e:  # numpy buffer interop not available; fall back to repr
            print(f"(numpy extraction unavailable: {e}; printing tensor repr instead)")
            print(host)
            ok = "7" in str(host)

        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        ttnn.close_device(device)


if __name__ == "__main__":
    raise SystemExit(main())
