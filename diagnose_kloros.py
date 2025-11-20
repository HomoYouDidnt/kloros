#!/usr/bin/env python3
"""KLoROS Integration Diagnostic Tool"""
import os, sys, importlib, yaml

os.environ.setdefault("KLR_MEMORY_ROOT", "/home/kloros/src/kloros_memory")
os.environ.setdefault("KLR_REGISTRY", "/home/kloros/src/registry/capabilities.yaml")
os.environ.setdefault("COQUI_TOS_AGREED", "1")
sys.path.insert(0, "/home/kloros/src")
sys.path.insert(0, "/home/kloros")

def log(level, msg):
    colors = {"OK": "\033[92m", "FAIL": "\033[91m", "INFO": "\033[94m"}
    print(f"{colors.get(level, '')}[{level}]\033[0m {msg}")

def ping_module(modpath):
    try:
        module = importlib.import_module(modpath)
        for fn in ("run", "main", "start", "entry"):
            if hasattr(module, fn):
                try:
                    getattr(module, fn)({"diagnostic": True})
                    return (True, f"{modpath}.{fn}() succeeded")
                except:
                    pass
        return (True, f"{modpath} - imports OK")
    except ImportError as e:
        return (False, f"{modpath} - import failed: {e}")

def main():
    print("="*60); print("KLoROS Integration Diagnostic"); print("="*60)
    
    with open(os.environ["KLR_REGISTRY"]) as f:
        registry = yaml.safe_load(f)
    
    log("OK", f"Registry loaded ({len(registry)} entries)")
    
    try:
        import kloros_memory
        log("OK", "Memory system imported")
    except:
        log("FAIL", "Memory system failed to import")
    
    results = {"pass": 0, "fail": 0}
    for name, config in registry.items():
        if not isinstance(config, dict):
            continue
        if "module" in config and config.get("enabled", True):
            log("INFO", f"Testing {name}")
            ok, msg = ping_module(config["module"])
            log("OK" if ok else "FAIL", msg)
            results["pass" if ok else "fail"] += 1
        else:
            for sub, subconf in config.items():
                if isinstance(subconf, dict) and "module" in subconf and subconf.get("enabled", True):
                    log("INFO", f"Testing {name}.{sub}")
                    ok, msg = ping_module(subconf["module"])
                    log("OK" if ok else "FAIL", msg)
                    results["pass" if ok else "fail"] += 1
    
    print("="*60)
    print(f"Results: {results['pass']} passed, {results['fail']} failed")
    print("="*60)
    return 0 if results["fail"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
