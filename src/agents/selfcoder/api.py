import subprocess, shlex

def start_task(name: str):
    subprocess.run(f"/home/kloros/src/selfcoder/selfcoder.py {shlex.quote(name)} plan",
                   shell=True, check=True)

def make_single_file_patch(name: str, file: str, find: str, replace: str):
    subprocess.run(f"/home/kloros/src/selfcoder/selfcoder.py {shlex.quote(name)} patch {shlex.quote(file)} {shlex.quote(find)} {shlex.quote(replace)}",
                   shell=True, check=True)

def apply(name: str):
    subprocess.run(f"/home/kloros/src/selfcoder/selfcoder.py {shlex.quote(name)} apply",
                   shell=True, check=True)
