#!/usr/bin/env python3
"""
D-REAM continuous evolutionary runner with class-based evaluator support.
Supports module-level functions, factory functions, and class-based evaluators.
"""
import argparse, os, sys, time, json, pathlib, itertools, importlib.util, math, copy, random, signal, inspect
from concurrent.futures import ProcessPoolExecutor, TimeoutError
import threading
from collections import defaultdict
from functools import reduce
import operator

# ------------------- small utils -------------------
def load_yaml(path):
    import yaml
    with open(path, "r") as f:
        return yaml.safe_load(f)

def ensure_dir(p): pathlib.Path(p).mkdir(parents=True, exist_ok=True)
def now_ts(): return int(time.time())
def write_jsonl(path, rec):
    with open(path, "a") as f: f.write(json.dumps(rec) + "\n")

# ------------------- adaptive search space state -------------------
_space_locks = defaultdict(threading.Lock)
_fitness_hist = defaultdict(list)
_coverage_seen = defaultdict(set)

def _safe_product_cardinality(space: dict) -> int:
    """Overflow-proof cartesian product size."""
    sizes = [max(1, len(v)) for v in space.values()]
    return reduce(operator.mul, sizes, 1) if sizes else 0

def _log_space_adaptation(logdir, exp_name, gen, trigger, old_space, new_space):
    """Log adaptation event with per-param diffs."""
    diffs = {
        k: {
            "old": old_space.get(k),
            "new": new_space.get(k),
            "delta_size": len(new_space.get(k, [])) - len(old_space.get(k, []))
        }
        for k in sorted(set(old_space) | set(new_space))
        if old_space.get(k) != new_space.get(k)
    }

    rec = {
        "event": "search_space_adapted",
        "experiment": exp_name,
        "generation": gen,
        "trigger": trigger,
        "space_size_before": _safe_product_cardinality(old_space),
        "space_size_after": _safe_product_cardinality(new_space),
        "changes": diffs
    }

    out = pathlib.Path(logdir) / f"{exp_name}.jsonl"
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

def cartesian(search_space: dict):
    if not search_space:
        yield {}; return
    keys = list(search_space.keys())
    vals = [search_space[k] for k in keys]
    for combo in itertools.product(*vals):
        yield {k: v for k, v in zip(keys, combo)}

# ------------------- evaluator loading (class + function support) -------------------
def _import_module_from_path(path):
    spec = importlib.util.spec_from_file_location("_dreameval_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # Register in sys.modules for Python 3.13 dataclass compatibility
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def _build_context(exp_name, exp_cfg, run_cfg, gen_idx=None):
    """Build context dict for evaluators that accept it."""
    return {
        "experiment": exp_name,
        "generation": gen_idx,
        "budget": exp_cfg.get("budget", {}),
        "run": run_cfg,
        "timestamp": now_ts(),
    }

def _resolve_evaluator_callable(evaluator_cfg_or_path):
    """
    Returns a tuple (callable_or_obj, call_style)
      call_style in {"fn", "method"}:
         - "fn": a plain callable (evaluate)
         - "method": an object exposing .evaluate(...)
    Supports:
      - path + symbol
      - path + factory (factory returns object with .evaluate)
      - path + class (instantiate, then use .evaluate)
      - legacy: plain path with module-level evaluate
    """
    if isinstance(evaluator_cfg_or_path, dict):
        path = evaluator_cfg_or_path.get("path")
        symbol = evaluator_cfg_or_path.get("symbol")
        factory = evaluator_cfg_or_path.get("factory")
        klass = evaluator_cfg_or_path.get("class")
        init_kwargs = evaluator_cfg_or_path.get("init_kwargs", {}) or {}
        if not path:
            raise RuntimeError("evaluator.path is required when using evaluator:{} block")
        mod = _import_module_from_path(path)

        if symbol:
            fn = getattr(mod, symbol, None)
            if not callable(fn):
                raise RuntimeError(f"{path} has no callable symbol {symbol}()")
            return fn, "fn"

        if factory:
            fac = getattr(mod, factory, None)
            if not callable(fac):
                raise RuntimeError(f"{path} has no factory {factory}()")
            obj = fac(**init_kwargs) if init_kwargs else fac()
            if not hasattr(obj, "evaluate") or not callable(getattr(obj, "evaluate")):
                raise RuntimeError(f"{path}:{factory} did not return an object with .evaluate()")
            return obj, "method"

        if klass:
            C = getattr(mod, klass, None)
            if C is None:
                raise RuntimeError(f"{path} has no class {klass}")
            obj = C(**init_kwargs) if init_kwargs else C()
            if not hasattr(obj, "evaluate") or not callable(getattr(obj, "evaluate")):
                raise RuntimeError(f"{path}:{klass} has no callable .evaluate()")
            return obj, "method"

        # fallback: try module-level evaluate
        fn = getattr(mod, "evaluate", None)
        if callable(fn):
            return fn, "fn"
        raise RuntimeError(f"{path} does not expose evaluate(), factory, or class evaluator")
    else:
        # legacy string path
        path = evaluator_cfg_or_path
        mod = _import_module_from_path(path)
        fn = getattr(mod, "evaluate", None)
        if not callable(fn):
            raise RuntimeError(f"{path} does not expose module-level evaluate()")
        return fn, "fn"

def _call_evaluator(callable_or_obj, call_style, params, context):
    """
    Calls evaluator with best-effort signature matching:
      - evaluate(params, context)
      - evaluate(params)
      - evaluate(config)   (legacy 'config' naming)
    """
    if call_style == "fn":
        sig = inspect.signature(callable_or_obj)
        if len(sig.parameters) == 2:
            return callable_or_obj(params, context)
        else:
            # accept either 'params' or 'config' naming; both are dicts
            return callable_or_obj(params)
    else:
        m = getattr(callable_or_obj, "evaluate")
        sig = inspect.signature(m)
        # skip 'self' parameter for methods
        params_count = len([p for p in sig.parameters.values() if p.name != 'self'])
        if params_count == 2:
            return m(params, context)
        else:
            return m(params)

# ------------------- pluggable components -------------------
def weighted_score(metrics: dict, weights: dict):
    return sum(float(metrics.get(k, 0.0)) * float(w) for k, w in (weights or {}).items())

def aggregator_score(method: str, metrics: dict, weights: dict):
    method = (method or "weighted_sum").lower()
    if method == "weighted_sum":
        return weighted_score(metrics, weights)
    # future: pareto, etc. (keep API stable)
    return weighted_score(metrics, weights)

def selector_rzero(scored, cfg):
    k = int(cfg.get("tournament_size", 4)); keep = int(cfg.get("survivors", 2))
    out = []
    for i in range(0, len(scored), max(1, k)):
        chunk = sorted(scored[i:i+k], key=lambda x: x.get("fitness", -1e18), reverse=True)
        out.extend(chunk[:keep])
    return out

def select(kind: str, scored, cfg):
    kind = (kind or "rzero").lower()
    if kind == "rzero": return selector_rzero(scored, cfg)
    return selector_rzero(scored, cfg)

def mutate_gaussian(params: dict, sigma=0.15):
    out = dict(params)
    for k, v in list(out.items()):
        if isinstance(v, (int, float)):
            jitter = (sigma * v) if v != 0 else sigma
            out[k] = type(v)(v + random.gauss(0, jitter))
    return out

def mutate_categorical(params: dict, search_space: dict, p=0.25):
    out = dict(params)
    for k, choices in (search_space or {}).items():
        if isinstance(choices, (list, tuple)) and choices and random.random() < p:
            out[k] = random.choice(choices)
    return out

def apply_mutators(base_params: dict, mutators_cfg: list, search_space: dict):
    p = dict(base_params)
    for m in (mutators_cfg or []):
        kind = (m.get("kind","") or "").lower()
        if kind == "numeric":
            p = mutate_gaussian(p, float(m.get("sigma", 0.15)))
        elif kind == "categorical":
            p = mutate_categorical(p, search_space, float(m.get("p", 0.25)))
    return p

def map_metrics(raw: dict, mapping: dict):
    if not mapping: return raw.copy()
    out = raw.copy()
    for src, dst in mapping.items():
        if src in raw: out[dst] = raw[src]
    return out

# ------------------- survivor pool -------------------
def survivors_path(artifact_root, exp_name):
    p = pathlib.Path(artifact_root) / "survivors"; ensure_dir(p); return p / f"{exp_name}.json"

def load_survivors(artifact_root, exp_name, default_pop):
    p = survivors_path(artifact_root, exp_name)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, list) and data: return data
        except Exception: pass
    return default_pop

def save_survivors(artifact_root, exp_name, survivors):
    p = survivors_path(artifact_root, exp_name)
    with open(p, "w") as f:
        json.dump(survivors, f, indent=2)

# ------------------- sandboxed evaluator -------------------
def _eval_entry(args):
    (evaluator_spec, params, allow_gpu, exp_name, exp_cfg, run_cfg, gen_idx) = args
    if not allow_gpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ.setdefault("OMP_NUM_THREADS","1")
    os.environ.setdefault("MKL_NUM_THREADS","1")

    callable_or_obj, style = _resolve_evaluator_callable(evaluator_spec)
    ctx = _build_context(exp_name, exp_cfg, run_cfg, gen_idx)
    return _call_evaluator(callable_or_obj, style, copy.deepcopy(params), ctx)

def evaluate_population(exp_name, population, evaluator_spec, allow_gpu, wallclock, logdir, agg_cfg, exp_cfg, run_cfg, gen_idx):
    per_exp_jsonl = pathlib.Path(logdir) / f"{exp_name}.jsonl"
    default_weights = (agg_cfg or {}).get("weights", {}) or {}
    method = (agg_cfg or {}).get("method", "weighted_sum")
    mapping = (exp_cfg.get("metrics", {}) or {}).get("map", {}) or {}
    directions = (exp_cfg.get("metrics", {}) or {}).get("target_direction", {}) or {}
    override_w = (exp_cfg.get("overrides", {}) or {}).get("fitness_weights")

    results = []
    with ProcessPoolExecutor(max_workers=max(1, int(os.environ.get("DREAM_MAX_WORKERS", "0")) or  os.cpu_count()//2)) as pool:
        futs = [(cand, pool.submit(_eval_entry, (evaluator_spec, cand, allow_gpu, exp_name, exp_cfg, run_cfg, gen_idx))) for cand in population]
        for cand, fut in futs:
            rec = { "ts": now_ts(), "experiment": exp_name, "params": cand }
            try:
                raw = fut.result(timeout=wallclock)
                canon = map_metrics(raw, mapping)
                # choose weights: per-exp override wins; otherwise derive sign from directions
                weights = copy.deepcopy(default_weights)
                if override_w is not None:
                    weights = copy.deepcopy(override_w)
                else:
                    # if directions specify "down", flip sign of weight (default weight=1.0)
                    for k, dirn in directions.items():
                        dst = mapping.get(k, k)
                        if dst not in weights: weights[dst] = 1.0
                        weights[dst] = -abs(weights[dst]) if str(dirn).lower()=="down" else abs(weights[dst])
                rec["raw_metrics"] = raw
                rec["canonical_metrics"] = canon
                rec["fitness"] = aggregator_score(method, canon, weights)
            except TimeoutError:
                rec["error"] = f"timeout_{wallclock}s"; rec["fitness"] = -1e18
            except Exception as e:
                rec["error"] = repr(e); rec["fitness"] = -1e18
            results.append(rec); write_jsonl(per_exp_jsonl, rec)
    return results

def save_generation(exp_dir, gen_idx, results):
    ensure_dir(exp_dir)
    with open(pathlib.Path(exp_dir) / f"gen_{gen_idx}_candidates.jsonl", "w") as f:
        for r in results: f.write(json.dumps(r) + "\n")

# ------------------- one experiment, multi-gen -------------------
def run_experiment(exp_cfg, run_cfg, agg_cfg, logdir):
    if not exp_cfg.get("enabled", True): return
    exp_name = exp_cfg["name"]

    # Support both new evaluator:{} block and legacy domain_evaluator string
    evaluator_spec = exp_cfg.get("evaluator") or exp_cfg.get("domain_evaluator")

    budget = exp_cfg.get("budget", {})
    wallclock = int(budget.get("wallclock_sec", 300))
    allow_gpu = bool(budget.get("allow_gpu", False))
    max_candidates = int(budget.get("max_candidates", 8))
    generations = int(budget.get("max_generations", 4))

    artifact_root = run_cfg.get("artifact_root") or "./artifacts/dream"
    ts = now_ts()
    exp_dir = pathlib.Path(artifact_root) / exp_name / str(ts)
    ensure_dir(exp_dir)

    # seed population: cartesian bounded or [{}]
    seed = list(itertools.islice(cartesian(exp_cfg.get("search_space", {})), max_candidates)) or [{}]
    # try to load survivors from prior cycles; fall back to seed
    population = load_survivors(artifact_root, exp_name, seed)[:max_candidates]

    # selection config (pluggable; default rzero)
    selector_cfg = (exp_cfg.get("selector") or exp_cfg.get("rzero") or {})
    selector_kind = (exp_cfg.get("selector", {}) or {}).get("kind", "rzero")

    mutators_cfg = exp_cfg.get("mutators") or []  # per-exp mutators
    if not mutators_cfg:  # fallback to global mutators
        mutators_cfg = (run_cfg.get("mutators") or []) + ( (exp_cfg.get("overrides") or {}).get("mutators") or [])

    best_overall = None
    plateau_count = 0
    plateau_patience = int((exp_cfg.get("convergence") or {}).get("patience_gens", 0))

    for gen in range(max(1, generations)):
        results = evaluate_population(exp_name, population, evaluator_spec, allow_gpu, wallclock, logdir, agg_cfg, exp_cfg, run_cfg, gen)
        save_generation(exp_dir, gen, results)

        # best this gen
        best = max(results, key=lambda x: x.get("fitness", -1e18))
        if best_overall is None or best["fitness"] > best_overall["fitness"]:
            best_overall = best; plateau_count = 0
        else:
            plateau_count += 1

        # select survivors
        sorted_results = sorted(results, key=lambda x: x.get("fitness", -1e18), reverse=True)
        survivors = select(selector_kind, sorted_results, selector_cfg)

        # --- adaptive search space (if enabled) ---
        search_space_cfg = exp_cfg.get("search_space", {})
        if isinstance(search_space_cfg, dict) and search_space_cfg.get("adaptive", False):
            try:
                from adaptive_search_space import AdaptiveSearchSpaceManager

                # Track fitness history
                _fitness_hist[exp_name].append(best.get("fitness", -1e18))

                # Build current discrete space
                current_space = {
                    k: (v.get("initial", v) if isinstance(v, dict) else v)
                    for k, v in search_space_cfg.items()
                    if k not in ("adaptive",)
                }

                mgr = AdaptiveSearchSpaceManager(exp_cfg)
                if mgr.should_adapt(gen, _fitness_hist[exp_name], best.get("params", {})):
                    trigger = mgr.get_trigger() or "unknown"
                    new_space = mgr.adapt_space(
                        trigger, _fitness_hist[exp_name], best.get("params", {}), current_space
                    )
                    ok, why = mgr.validate_bounds(new_space)
                    if ok:
                        with _space_locks[exp_name]:
                            # Persist back to config
                            for pk, vals in new_space.items():
                                block = search_space_cfg.get(pk, {})
                                if isinstance(block, dict) and "initial" in block:
                                    block["initial"] = list(vals)
                                else:
                                    search_space_cfg[pk] = list(vals)
                        _log_space_adaptation(logdir, exp_name, gen, trigger, current_space, new_space)
                    else:
                        import logging
                        logging.warning(f"adaptive_blocked exp={exp_name} gen={gen} reason={'; '.join(why)}")
            except Exception as e:
                import logging
                logging.error(f"adaptive_error exp={exp_name} gen={gen} error={repr(e)}")

        # reinsertion: elitism + mutated survivors + fresh random injects
        elitism = int(selector_cfg.get("elitism", 1))
        fresh = int(selector_cfg.get("fresh_inject", 2))

        next_pop = [s["params"] for s in survivors[:elitism]]
        for s in survivors:
            child = apply_mutators(s["params"], mutators_cfg, exp_cfg.get("search_space", {}))
            next_pop.append(child)

        # diversity
        for _ in range(fresh):
            rnd = {k: random.choice(vs) for k, vs in (exp_cfg.get("search_space", {})).items()} if exp_cfg.get("search_space") else {}
            next_pop.append(rnd)

        # cap for next gen
        population = next_pop[:max_candidates]

        # early stop on convergence, if configured
        if plateau_patience and plateau_count >= plateau_patience:
            break

    # write summary + rolling winner + survivors pool
    summary = {
        "ts": ts, "experiment": exp_name,
        "best_fitness": best_overall.get("fitness") if best_overall else None,
        "best_params": best_overall.get("params") if best_overall else None,
        "best_metrics": best_overall.get("raw_metrics") if best_overall else None,
        "generations": gen + 1,
    }
    with open(pathlib.Path(exp_dir) / "summary.json", "w") as f: json.dump(summary, f, indent=2)
    winners_dir = pathlib.Path(artifact_root) / "winners"; ensure_dir(winners_dir)
    with open(winners_dir / f"{exp_name}.json", "w") as f:
        json.dump({"updated_at": now_ts(), "best": {
            "fitness": summary["best_fitness"],
            "params": summary["best_params"],
            "metrics": summary["best_metrics"],
        }}, f, indent=2)

    # persist survivors (params only) for next cycle start
    save_survivors(artifact_root, exp_name, [s["params"] for s in survivors])

# ------------------- remediation experiments -------------------
def inject_remediation_experiments(cfg, logdir):
    """
    Check for approved remediation experiments and inject into config.

    Uses the refactored architecture with proper type hierarchy and
    clean separation of concerns.

    Returns:
        Modified config with remediation experiments added
    """
    try:
        import sys
        import os
        import logging
        from pathlib import Path
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

        from experiment_repository import ExperimentRepository
        from remediation_service import (
            RemediationExperimentGenerator,
            ApprovalService,
            ExperimentInjector
        )

        generator = RemediationExperimentGenerator()
        repository = ExperimentRepository(
            Path("/home/kloros/.kloros/remediation_approved.json")
        )
        approval_service = ApprovalService(repository)

        proposed = generator.generate_remediation_experiments(min_priority=0.6)

        if not proposed:
            logging.debug("[remediation] No remediation experiments proposed")
            return cfg

        autonomy_level = int(os.environ.get("KLR_AUTONOMY_LEVEL", "0"))
        approved = approval_service.get_experiments_to_approve(
            proposed, autonomy_level
        )

        if not approved:
            logging.info("[remediation] No experiments approved")
            return cfg

        return ExperimentInjector.inject_experiments(cfg, approved)

    except Exception as e:
        import logging
        import traceback
        logging.error(f"[remediation] Failed to inject experiments: {e}")
        logging.error(f"[remediation] Traceback: {traceback.format_exc()}")
        return cfg


# ------------------- cycle & main loop -------------------
def run_cycle(cfg, logdir):
    run_cfg = cfg.get("run", {})
    agg_cfg = cfg.get("fitness_aggregation", {"method":"weighted_sum","weights":{}})
    ensure_dir(run_cfg.get("artifact_root") or "./artifacts/dream"); ensure_dir(logdir)

    # Inject remediation experiments (if any)
    cfg = inject_remediation_experiments(cfg, logdir)

    # Get all experiments
    all_experiments = cfg.get("experiments", [])

    # Filter to enabled experiments only
    enabled_experiments = [exp for exp in all_experiments if exp.get("enabled", True)]

    if not enabled_experiments:
        print("[D-REAM] No enabled experiments to run")
        return

    # Use reasoning to prioritize experiments via VOI
    try:
        from src.reasoning_coordinator import get_reasoning_coordinator
        coordinator = get_reasoning_coordinator()

        print(f"[D-REAM] 🧠 Using reasoning to prioritize {len(enabled_experiments)} enabled experiments")

        # Calculate VOI for each experiment
        for exp in enabled_experiments:
            exp['_voi'] = coordinator.calculate_voi({
                'action': f"Run D-REAM experiment: {exp.get('name', 'unknown')}",
                'experiment_name': exp.get('name', 'unknown'),
                'enabled': exp.get('enabled', True),
                'budget': exp.get('budget', {}),
                'search_space_size': len(exp.get('search_space', {}))
            })

        # Sort by VOI (highest first)
        prioritized_experiments = sorted(enabled_experiments, key=lambda e: e.get('_voi', 0.0), reverse=True)

        print("[D-REAM] Experiment priorities (VOI-ranked):")
        for i, exp in enumerate(prioritized_experiments, 1):
            voi = exp.get('_voi', 0.0)
            name = exp.get('name', 'unknown')
            print(f"[D-REAM]   #{i}: {name} (VOI: {voi:.3f})")

        experiments_to_run = prioritized_experiments

    except Exception as e:
        print(f"[D-REAM] ⚠️ Reasoning failed, running all enabled experiments: {e}")
        experiments_to_run = enabled_experiments

    # Run prioritized experiments
    for exp in experiments_to_run:
        run_experiment(exp, run_cfg, agg_cfg, logdir)

def is_phase_window():
    """Check if current time is in PHASE overnight window (3-7 AM)."""
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    return 3 <= hour < 7

def sleep_until_phase_ends():
    """Sleep until PHASE window ends (7 AM)."""
    from datetime import datetime, timedelta
    while is_phase_window():
        now = datetime.now()
        # Calculate seconds until 7 AM
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now.hour >= 7:
            target += timedelta(days=1)
        sleep_sec = (target - now).total_seconds()
        # Sleep in 60-second chunks to allow for clean shutdown
        sleep_chunk = min(60, sleep_sec)
        print(f"[D-REAM] PHASE window active (3-7 AM). Sleeping {int(sleep_sec/60)} minutes until 7 AM...", flush=True)
        time.sleep(sleep_chunk)

def main():
    ap = argparse.ArgumentParser("D-REAM background evolutionary runner")
    ap.add_argument("--config", required=True)
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--epochs-per-cycle", type=int, default=1)
    ap.add_argument("--max-parallel", type=int, default=1)  # reserved; worker count is computed inside
    ap.add_argument("--sleep-between-cycles", type=int, default=0)
    args = ap.parse_args()

    # hot-reload flag (SIGHUP)
    reload_flag = {"set": False}
    def _hup(_sig, _frm): reload_flag["set"] = True
    signal.signal(signal.SIGHUP, _hup)

    while True:
        # Check if we're in PHASE window - if so, sleep until it ends
        if is_phase_window():
            sleep_until_phase_ends()

        cfg = load_yaml(args.config)
        # allow per-runner default mutators at top-level
        run_cycle(cfg, args.logdir)
        # if HUP received, next loop will read new YAML
        reload_flag["set"] = False
        if args.epochs_per_cycle <= 1 and (args.sleep_between_cycles or 0) == 0:
            break
        # continuous background behavior (D-REAM style)
        for _ in range(max(1, int(args.epochs_per_cycle)) - 1):
            # Check again before each cycle
            if is_phase_window():
                sleep_until_phase_ends()
            cfg = load_yaml(args.config)
            run_cycle(cfg, args.logdir)
            if args.sleep_between_cycles > 0:
                time.sleep(args.sleep_between_cycles)
        if args.sleep_between_cycles > 0:
            time.sleep(args.sleep_between_cycles)

if __name__ == "__main__":
    sys.exit(main())
