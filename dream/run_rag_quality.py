import os, json, time, yaml, subprocess, shlex, pathlib, re
EXP = pathlib.Path("/home/kloros/dream/experiments/rag_quality.yaml")
GOLD = pathlib.Path("/home/kloros/dream/golden/rag_golden.json")
SC   = "/home/kloros/src/selfcoder/selfcoder.py"
PYTHON = "/home/kloros/.venv/bin/python3"

def run(cmd, check=True):
    print("[$]", cmd)
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout

def verify():
    return run("/home/kloros/scripts/verify_all.sh")

def eval_quality():
    import importlib
    rag = importlib.import_module("rag.pipeline")
    data = json.load(open(GOLD))
    total, hits, mrr_sum = 0, 0, 0.0
    for item in data:
        q = item["query"]
        res = rag.retrieve(q, topk=5)
        docs = " ".join([r.get("text","") for r in res])
        ok = all(kw.lower() in docs.lower() for kw in item["keywords"])
        hits += 1 if ok else 0
        rr = 0.0
        for i,r in enumerate(res, start=1):
            text = r.get("text","").lower()
            if any(kw.lower() in text for kw in item["keywords"]):
                rr = 1.0 / i; break
        mrr_sum += rr
        total += 1
    hit_rate = hits / max(1,total)
    mrr = mrr_sum / max(1,total)
    return {"hit_rate@5": hit_rate, "mrr@5": mrr}

def apply_fusion(task, a, b):
    srcs = ["/home/kloros/src/rag/hybrid.py", "/home/kloros/src/rag/pipeline.py"]
    for src in srcs:
        try:
            run(f"{PYTHON} {SC} {task} patch {src} '0.5*b + 0.5*v' '{a}*b + {b}*v'", check=False)
            run(f"{PYTHON} {SC} {task} patch {src} '0.5*b+0.5*v' '{a}*b+{b}*v'", check=False)
        except Exception as e:
            print(f'no-op on {src}: {e}')

def main():
    os.environ.setdefault("KLR_REGISTRY","/home/kloros/src/registry/capabilities.yaml")
    cfg = yaml.safe_load(EXP.read_text())
    task = f"dream-{cfg['name']}-{int(time.time())}"
    run(f"{PYTHON} {SC} {task} plan")

    base_q = eval_quality()
    print(f"[BASE] {base_q}")
    best_fit = base_q["hit_rate@5"]*0.5 + base_q["mrr@5"]*0.5
    best_desc = "baseline"

    for mut in cfg["mutations"]:
        if not mut.startswith("fusion:"): 
            print(f"[SKIP] {mut}")
            continue
        a,b = mut.split(":")[1].split(",")
        try:
            run(f"{PYTHON} {SC} {task} plan")
            apply_fusion(task, a, b)
            run(f"{PYTHON} {SC} {task} apply")
            verify()
            q = eval_quality()
            fit = q["hit_rate@5"]*0.5 + q["mrr@5"]*0.5
            print(f"[FIT] fusion {a}/{b}: {q} -> {fit:.4f}")
            if fit > best_fit:
                best_fit, best_desc = fit, f"fusion {a}/{b}"
        except Exception as e:
            print(f"[FAIL] {mut}: {e}")
            continue

    print(f"[BEST] {best_desc}  fitness={best_fit:.4f}")

if __name__ == "__main__":
    main()
