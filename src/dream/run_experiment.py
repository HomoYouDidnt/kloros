import os, subprocess, time, yaml, shlex, pathlib, re

EXP = pathlib.Path("/home/kloros/src/dream/experiments/voice_latency.yaml")
SC  = "/home/kloros/src/selfcoder/selfcoder.py"

def run(cmd, check=True):
    print("[$]", cmd)
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout

def verify_and_measure():
    t0=time.time()
    out = run("/home/kloros/scripts/verify_all.sh")
    t_verify = int((time.time()-t0)*1000)
    # ASR latency parse
    asr_raw = run("python /home/kloros/scripts/verify_asr_vad.py /tmp/e2e_voice_reply.wav || true")
    m = re.search(r"\(([\d.]+)s\)", asr_raw)
    asr_ms = int(float(m.group(1))*1000) if m else 999999
    # TTS latency (optional parse hook if you add timing to smoke_tts.py)
    tts_ms = 0
    return {"verify_pass": True, "verify_ms": t_verify, "asr_latency_ms": asr_ms, "tts_latency_ms": tts_ms}

def fitness(score, cfg):
    if not score.get("verify_pass"): return -10**9, "verify_failed"
    s = 0.0
    for g in cfg["fitness"]["goals"]:
        k, w = g["id"], g["weight"]
        v = score.get(k, 0)
        if k.endswith("_ms"):
            v = -v  # lower is better
        s += w * v
    return s, ""

def apply_mutation(task, mtype):
    if mtype.startswith("replace_env_default:"):
        # replace os.environ.get("VAR","old") -> ("VAR","new")
        spec = mtype.split(":")[1:]
        var, pair = spec[0], spec[1]
        old, new = pair.split("->")
        src = "/home/kloros/src/kloros_voice.py"
        before = f'os.environ.get("{var}", "{old}")'
        after  = f'os.environ.get("{var}", "{new}")'
        run(f"python {SC} {task} patch {src} {shlex.quote(before)} {shlex.quote(after)}")
    elif mtype == "enable_streaming_xtts_chunks":
        src="/home/kloros/src/tts/router.py"
        run(f"python {SC} {task} patch {src} 'stream_chunks=False' 'stream_chunks=True'")
    elif mtype.startswith("adjust_vad_window"):
        src="/home/kloros/src/kloros_voice.py"
        old,new = mtype.split(':')[1].split('->')
        run(f"python {SC} {task} patch {src} {old} {new}")
    else:
        raise RuntimeError(f"unknown mutation {mtype}")

def main():
    cfg = yaml.safe_load(EXP.read_text())
    task = f"dream-{cfg['name']}-{int(time.time())}"
    os.environ.setdefault("KLR_REGISTRY","/home/kloros/src/registry/capabilities.yaml")

    # scaffold task & evidence
    run(f"python {SC} {task} plan")

    best_score, best_mut = -10**9, None
    for mut in cfg["mutations"]:
        try:
            # rebuild plan (append evidence), apply patch, then run verification
            run(f"python {SC} {task} plan")
            apply_mutation(task, mut)
            run(f"python {SC} {task} apply")
            score = verify_and_measure()
            fit,_ = fitness(score, cfg)
            print(f"[FIT] {mut}: {fit:.2f}  score={score}")
            if fit > best_score:
                best_score, best_mut = fit, mut
        except Exception as e:
            print(f"[FAIL] {mut}: {e}")

    print(f"[BEST] {best_mut}  fitness={best_score:.2f}")

if __name__ == "__main__":
    main()
