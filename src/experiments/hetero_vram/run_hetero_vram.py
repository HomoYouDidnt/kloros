#!/usr/bin/env python3
# src/experiments/hetero_vram/run_hetero_vram.py
import os, time, json, math, argparse, contextlib
from dataclasses import dataclass
from typing import Dict, Any, List

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from torch.cuda import nvml
except (ImportError, AttributeError):
    # Fallback to pynvml if torch.cuda.nvml is not available
    import pynvml as nvml

# ---------- Utils ----------
def init_nvml():
    nvml.nvmlInit()

def gpu_name(i):
    name = nvml.nvmlDeviceGetName(nvml.nvmlDeviceGetHandleByIndex(i))
    return name.decode() if isinstance(name, bytes) else name

def gpu_mem_gib(i):
    h = nvml.nvmlDeviceGetHandleByIndex(i)
    info = nvml.nvmlDeviceGetMemoryInfo(h)
    return ((info.total-info.free)/ (1024**3), info.total/(1024**3))  # used GiB, total GiB

def gpu_peak_snapshot(n_gpus):
    return {f"cuda:{i}": {"used_gib": round(gpu_mem_gib(i)[0],2),
                          "total_gib": round(gpu_mem_gib(i)[1],2)} for i in range(n_gpus)}

def device_ok(i):
    return torch.cuda.get_device_capability(i)

def can_p2p(i,j):
    try:
        return torch.cuda.device_can_access_peer(i, j)
    except Exception:
        return False

@contextlib.contextmanager
def timer():
    t0 = time.perf_counter()
    yield
    dt = time.perf_counter()-t0
    print(f"[timer] {dt:.3f}s")

def set_env_defaults():
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")

def dyn_budget_strings(safety=(0.5, 1.0)):
    """
    Compute dynamic VRAM budgets based on current usage.

    Args:
        safety: (cuda:0 safety, cuda:1 safety) in GiB - safety margin to prevent OOM

    Returns:
        (max_memory_dict, free_gib_tuple, raw_usage_tuple)
    """
    def snap(i):
        h = nvml.nvmlDeviceGetHandleByIndex(i)
        mem = nvml.nvmlDeviceGetMemoryInfo(h)
        used = mem.used / (1024**3)
        total = mem.total / (1024**3)
        return used, total

    used0, tot0 = snap(0)
    used1, tot1 = snap(1)
    b0 = max(tot0 - used0 - safety[0], 0.0)
    b1 = max(tot1 - used1 - safety[1], 0.0)

    return (
        {0: f"{int(b0)}GiB", 1: f"{int(b1)}GiB"},
        (b0, b1),
        ((used0, tot0), (used1, tot1))
    )

# ---------- Mode A: Accelerate auto split ----------
def run_mode_a(model_id, prompt, max_new_tokens, mm0, mm1, dtype="fp16"):
    from accelerate import infer_auto_device_map, init_empty_weights
    from accelerate.utils import get_balanced_memory
    torch_dtype = torch.float16 if dtype=="fp16" else torch.float32

    # Inference-only optimizations
    torch.set_grad_enabled(False)
    torch.cuda.empty_cache()

    with init_empty_weights():
        model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch_dtype, _fast_init=True)

    max_memory = {0: mm0, 1: mm1}  # strings like "9GiB"
    device_map = infer_auto_device_map(model, max_memory=max_memory, no_split_module_classes=["LlamaDecoderLayer","MistralDecoderLayer"], dtype=torch_dtype)
    # materialize with weights:
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch_dtype, device_map=device_map)

    tok = AutoTokenizer.from_pretrained(model_id, use_fast=True)
    ids = tok(prompt, return_tensors="pt").to(next(model.parameters()).device)

    # warmup (small to minimize VRAM footprint)
    _ = model.generate(**ids, max_new_tokens=4)

    start = time.perf_counter()
    out = model.generate(**ids, max_new_tokens=max_new_tokens)
    dur = time.perf_counter() - start
    toks = out.shape[-1] - ids["input_ids"].shape[-1]
    tps = toks / dur if dur>0 else 0.0

    text = tok.decode(out[0], skip_special_tokens=True)[-512:]
    return {
        "mode":"A_accelerate_auto",
        "device_map": device_map,
        "tokens_per_sec": round(tps,3),
        "duration_s": round(dur,3),
        "sample_tail": text
    }

# ---------- Mode B: Manual pipeline split + dtype bridge ----------
class Bridge(torch.nn.Module):
    def __init__(self, to_device, to_dtype):
        super().__init__()
        self.to_device = to_device
        self.to_dtype = to_dtype
    def forward(self, x):
        return x.to(device=self.to_device, dtype=self.to_dtype, non_blocking=True)

def run_mode_b(model_id, prompt, max_new_tokens, split_at:int, d0_dtype="fp32", d1_dtype="fp16"):
    torch_dtype0 = torch.float32 if d0_dtype=="fp32" else torch.float16
    torch_dtype1 = torch.float32 if d1_dtype=="fp32" else torch.float16

    # Inference-only optimizations
    torch.set_grad_enabled(False)
    torch.cuda.empty_cache()

    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch_dtype1)  # base load
    tok = AutoTokenizer.from_pretrained(model_id, use_fast=True)

    # Move embeddings + first split_at layers to cuda:0 (1080 Ti), rest to cuda:1 (3080)
    model.model.embed_tokens = model.model.embed_tokens.to(device="cuda:0", dtype=torch_dtype0)
    for i, layer in enumerate(model.model.layers):
        dev = "cuda:0" if i < split_at else "cuda:1"
        dt = torch_dtype0 if dev=="cuda:0" else torch_dtype1
        model.model.layers[i] = layer.to(device=dev, dtype=dt)
    model.model.norm = model.model.norm.to(device="cuda:1", dtype=torch_dtype1)
    model.lm_head = model.lm_head.to(device="cuda:1", dtype=torch_dtype1)

    # Boundary bridge (after layer split point)
    model.bridge = Bridge("cuda:1", torch_dtype1)

    # Patch forward to insert bridge exactly once (between last cuda:0 layer and first cuda:1 layer)
    orig_forward = model.model.forward
    def patched_forward(**kwargs):
        out = kwargs
        # Run embeddings + [0..split_at-1] on cuda:0
        input_ids = kwargs["input_ids"]
        if input_ids.device.type != "cuda" or input_ids.device.index != 0:
            input_ids = input_ids.to("cuda:0")
        h = model.model.embed_tokens(input_ids)
        pos_ids = torch.arange(0, h.shape[1], device=h.device).unsqueeze(0)
        for i, layer in enumerate(model.model.layers):
            if i == split_at:
                # move activations to cuda:1 + dtype cast
                h = model.bridge(h)
            h = layer(h, position_ids=pos_ids)[0]
        h = model.model.norm(h)
        return {"last_hidden_state": h}
    model.model.forward = patched_forward

    # Generate on cuda:1 head
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    # warmup (small to minimize VRAM footprint)
    _ = model.generate(**ids, max_new_tokens=4)

    start = time.perf_counter()
    out = model.generate(**ids, max_new_tokens=max_new_tokens)
    dur = time.perf_counter() - start
    toks = out.shape[-1] - ids["input_ids"].shape[-1]
    tps = toks / dur if dur>0 else 0.0
    text = tok.decode(out[0], skip_special_tokens=True)[-512:]

    return {
        "mode":"B_manual_pipeline",
        "split_at": split_at,
        "dtypes": {"cuda:0": d0_dtype, "cuda:1": d1_dtype},
        "tokens_per_sec": round(tps,3),
        "duration_s": round(dur,3),
        "sample_tail": text
    }

# ---------- Main ----------
@dataclass
class RunCfg:
    model_id: str
    prompt: str
    max_new_tokens: int
    mm0: str
    mm1: str
    split_at: int

def main():
    set_env_defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--prompt", default="You are KLoROS. Briefly explain heterogenous multi-GPU execution.")
    parser.add_argument("--max_new_tokens", type=int, default=128)
    parser.add_argument("--mm0", default="9GiB")   # Fallback if dynamic fails
    parser.add_argument("--mm1", default="22GiB")  # Fallback if dynamic fails
    parser.add_argument("--split_at", type=int, default=-1)  # -1 = auto-tune based on VRAM
    parser.add_argument("--out", default="/tmp/hetero_vram_results.jsonl")
    parser.add_argument("--min_headroom", type=float, default=2.0, help="Minimum free GiB per GPU to proceed")
    args = parser.parse_args()

    n = torch.cuda.device_count()
    assert n >= 2, "Need at least 2 CUDA devices"
    init_nvml()

    meta = {
        "gpus": {f"cuda:{i}": {
            "name": gpu_name(i),
            "capability": list(device_ok(i)),
            "p2p_with_other": {f"cuda:{j}": can_p2p(i,j) for j in range(n) if j!=i}
        } for i in range(n)},
        "env": {
            "driver": torch.version.cuda,
            "torch": torch.__version__
        }
    }
    results: List[Dict[str,Any]] = []
    results.append({"event":"probe", "meta":meta, "vram": gpu_peak_snapshot(2)})

    # Compute dynamic VRAM budgets
    maxmem, (b0, b1), raw = dyn_budget_strings(safety=(0.5, 1.0))
    results.append({
        "event": "dyn_budgets",
        "max_memory": maxmem,
        "free_gib": {"cuda:0": round(b0, 2), "cuda:1": round(b1, 2)},
        "raw": {
            "cuda:0": {"used": round(raw[0][0], 2), "total": round(raw[0][1], 2)},
            "cuda:1": {"used": round(raw[1][0], 2), "total": round(raw[1][1], 2)}
        }
    })
    print(f"[hetero] Dynamic budgets: cuda:0={maxmem[0]}, cuda:1={maxmem[1]} (free: {b0:.1f}G, {b1:.1f}G)")

    # Skip if insufficient headroom
    if b0 < args.min_headroom or b1 < args.min_headroom:
        results.append({
            "event": "skipped_hardware",
            "reason": "insufficient_headroom",
            "threshold_gib": args.min_headroom,
            "free_gib": {"cuda:0": round(b0, 2), "cuda:1": round(b1, 2)}
        })
        print(f"[hetero] Skipping: insufficient headroom (need {args.min_headroom}G, have {b0:.1f}G, {b1:.1f}G)")

        with open(args.out, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"Wrote {args.out}")
        return

    # Auto-tune split_at based on free VRAM ratio
    total_free = b0 + b1 + 1e-9
    ratio_0 = b0 / total_free
    MODEL_DEPTH = 32  # Default for 7B models; could probe model.config.num_hidden_layers
    auto_split = max(1, min(MODEL_DEPTH - 1, int(MODEL_DEPTH * ratio_0 * 0.9)))
    split_at = args.split_at if args.split_at >= 0 else auto_split
    print(f"[hetero] Split point: {split_at} (auto-tuned from VRAM ratio {ratio_0:.2f})")

    # Mode A - Use dynamic budgets
    try:
        rA = run_mode_a(args.model, args.prompt, args.max_new_tokens,
                       maxmem[0], maxmem[1], dtype="fp16")
        results.append({"event":"modeA_done", "data": rA, "vram": gpu_peak_snapshot(2)})
        print(f"[hetero] Mode A succeeded: {rA['tokens_per_sec']} tok/s")
    except Exception as e:
        results.append({"event":"modeA_fail", "error": repr(e), "vram": gpu_peak_snapshot(2)})
        print(f"[hetero] Mode A failed: {e}")

    # Mode B - Use auto-tuned split
    try:
        rB = run_mode_b(args.model, args.prompt, args.max_new_tokens, split_at,
                       d0_dtype="fp32", d1_dtype="fp16")
        results.append({"event":"modeB_done", "data": rB, "vram": gpu_peak_snapshot(2)})
        print(f"[hetero] Mode B succeeded: {rB['tokens_per_sec']} tok/s (split={split_at})")
    except Exception as e:
        results.append({"event":"modeB_fail", "error": repr(e), "vram": gpu_peak_snapshot(2)})
        print(f"[hetero] Mode B failed: {e}")

    # Compute success flags
    flags = {}
    last = results[-1]
    vram_use = last.get("vram", gpu_peak_snapshot(2))
    both_used = all(vram_use[k]["used_gib"] > 2.0 for k in vram_use)
    flags["both_vram_used"] = both_used
    tps = 0.0
    for ev in results[::-1]:
        if "data" in ev and "tokens_per_sec" in ev["data"]:
            tps = ev["data"]["tokens_per_sec"]
            break
    flags["tokens_per_sec"] = tps
    results.append({"event":"summary", "flags": flags})

    with open(args.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {args.out}")

if __name__ == "__main__":
    main()
