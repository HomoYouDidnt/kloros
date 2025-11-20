# src/dream/runner/tools.py
import subprocess, pathlib

def run_cmd(cmd:str, cwd:str):
    p = subprocess.Popen(cmd, cwd=cwd, shell=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = p.communicate()
    return {"ok": p.returncode==0, "code": p.returncode, "out": out}

def run_pytest(test_cmd:str, workdir:str, artifacts_dir:str):
    res = run_cmd(test_cmd, workdir)
    pathlib.Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(artifacts_dir)/"post_test.log").write_text(res["out"])
    return res
