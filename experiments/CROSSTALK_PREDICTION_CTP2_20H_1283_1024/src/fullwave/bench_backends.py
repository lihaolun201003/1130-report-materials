"""Benchmark CPU-numpy vs torch-CUDA stencil throughput for scalar FDTD updates.

Run:  python bench_backends.py
Writes JSON to cache/fullwave/bench_backends.json
"""
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(BASE, "cache", "fullwave")
os.makedirs(CACHE, exist_ok=True)

DEV = "cuda" if torch.cuda.is_available() else "cpu"


def bench_torch(n1, n2, steps, dtype=torch.float32, lst=4):
    dev = torch.device(DEV)
    dt = dtype
    a = torch.randn(n1, n2, device=dev, dtype=dt)
    b = torch.randn(n1, n2, device=dev, dtype=dt)
    c = torch.empty_like(a)
    if lst == 2:
        w = torch.tensor([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]],
                         device=dev, dtype=dt).view(1, 1, 3, 3)
    else:
        w = torch.zeros(1, 1, 5, 5, device=dev, dtype=dt)
        w[0, 0, 2, 1] = 16.0
        w[0, 0, 2, 3] = 16.0
        w[0, 0, 1, 2] = 16.0
        w[0, 0, 3, 2] = 16.0
        w[0, 0, 2, 2] = -30.0
        w[0, 0, 2, 0] = -1.0
        w[0, 0, 2, 4] = -1.0
        w[0, 0, 0, 2] = -1.0
        w[0, 0, 4, 2] = -1.0
        w = w / 12.0
    pad = 2 if lst == 4 else 1
    torch.cuda.synchronize()
    t0 = time.time()
    for _ in range(steps):
        lap = F.conv2d(a.unsqueeze(0).unsqueeze(0), w, padding=pad).squeeze(0).squeeze(0)
        c = 2.0 * a - b + lap
        # emulate the two-field swap without copying: pointer swap
        a, b, c = c, a, b
    torch.cuda.synchronize()
    el = time.time() - t0
    return el


def bench_numpy(n1, n2, steps, lst=4):
    a = np.random.randn(n1, n2)
    b = np.random.randn(n1, n2)
    c = np.empty_like(a)
    if lst == 2:
        t0 = time.time()
        for _ in range(steps):
            lap = (a[2:, 1:-1] + a[:-2, 1:-1] + a[1:-1, 2:] + a[1:-1, :-2]
                   - 4.0 * a[1:-1, 1:-1])
            c[1:-1, 1:-1] = 2.0 * a[1:-1, 1:-1] - b[1:-1, 1:-1] + lap
            a, b, c = c, a, b
        return time.time() - t0
    t0 = time.time()
    for _ in range(steps):
        lap = (16.0 * (a[2:-2, 1:-3] + a[2:-2, 3:-1] + a[1:-3, 2:-2] + a[3:-1, 2:-2])
               - (a[2:-2, :-4] + a[2:-2, 4:] + a[:-4, 2:-2] + a[4:, 2:-2])
               - 30.0 * a[2:-2, 2:-2])
        c[2:-2, 2:-2] = 2.0 * a[2:-2, 2:-2] - b[2:-2, 2:-2] + lap
        a, b, c = c, a, b
    return time.time() - t0


if __name__ == "__main__":
    res = {}
    for (n1, n2, steps) in [(512, 512, 200), (1024, 1024, 100), (2048, 2048, 30)]:
        cells = n1 * n2
        for lst in (2, 4):
            et = bench_torch(n1, n2, steps, torch.float32, lst)
            upd = cells * steps / et
            res[f"torch_f32_lst{lst}_{n1}x{n2}"] = dict(sec=et, cell_updates_per_s=upd)
            print(f"torch f32 lst{lst} {n1}x{n2} {steps}: {et:.3f}s  {upd/1e9:.2f} Gcupd/s")
            if cells <= 2048 * 2048 and n1 <= 1024:
                en = bench_numpy(n1, n2, max(steps // 10, 5), lst)
                updn = cells * max(steps // 10, 5) / en
                res[f"numpy_f64_lst{lst}_{n1}x{n2}"] = dict(sec=en, cell_updates_per_s=updn)
                print(f"numpy f64 lst{lst} {n1}x{n2}: {en:.3f}s  {updn/1e9:.2f} Gcupd/s")
    if torch.cuda.is_available():
        try:
            et = bench_torch(1024, 1024, 50, torch.float64, 4)
            upd = 1024 * 1024 * 50 / et
            res["torch_f64_lst4_1024x1024"] = dict(sec=et, cell_updates_per_s=upd)
            print(f"torch f64 lst4 1024x1024: {et:.3f}s {upd/1e9:.2f} Gcupd/s")
        except Exception as e:
            print("fp64 conv failed:", e)
    with open(os.path.join(CACHE, "bench_backends.json"), "w") as f:
        json.dump(res, f, indent=2)
    print("device:", DEV)
