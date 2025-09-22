import contextlib
import io
import os
import runpy
import traceback

root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_dir = os.path.join(root, "src")
files = ["kloros_voice.py", "test_audio.py", "test_components.py", "rag.py", "rag_demo.py"]
results = {}
for fn in files:
    path = os.path.join(src_dir, fn)
    run_name = "loaded_" + fn[:-3]
    try:
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            # runpy.run_path will execute the module code in a fresh namespace
            runpy.run_path(path, run_name=run_name)
        out = buf_out.getvalue()
        err = buf_err.getvalue()
        results[fn] = ("ok", out, err)
    except Exception:
        results[fn] = ("error", traceback.format_exc(), "")

for fn, (status, out, err) in results.items():
    print("FILE:", fn, "STATUS:", status)
    if out:
        print("--- STDOUT ---")
        print(out.strip())
    if err:
        print("--- STDERR ---")
        print(err.strip())
    print("---")
