"""
run_paper_experiments.py – VRTPP-PR paper model scalability experiments.

Loads solve_vrtpp_pr and supporting definitions from VRTPP-PaperModel.ipynb
(verification-suite branch) and runs the same random-instance configurations
used by run_experiments.py, writing results into the 'paper' rows of results.csv.

Run from the repo root:
    python3 experiments/run_paper_experiments.py              # all missing configs
    python3 experiments/run_paper_experiments.py --config 1 4 # single config
"""

import argparse
import csv
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
REPO_ROOT   = SCRIPT_DIR.parent
RESULTS_CSV = SCRIPT_DIR / "results.csv"
NOTEBOOK    = REPO_ROOT / "VRTPP-PaperModel.ipynb"

# ── Settings — kept in sync with run_experiments.py ──────────────────────────
# Intentionally reduced from the paper's full setup (10 instances, longer
# limits) to keep exploratory runs fast. Results are indicative only.
#
# MIP gap is tiered by n_r, identical to run_experiments.py:
#   n_r=1 → MIPGap=0.00, n_r=2 → MIPGap=0.05, n_r=3 → MIPGap=0.10
# The gap used is recorded in the results.csv notes column.
ALL_CONFIGS = [
    (1, 4), (1, 6), (1, 8), (1, 10),
    (2, 4), (2, 6), (2, 8), (2, 10),
    (3, 4), (3, 6), (3, 8), (3, 10),
]
N_INSTANCES          = 3
BASE_SEED            = 42
MILP_TIME_LIMIT      = 30.0
MAX_ITERATIONS       = 50
CONVERGENCE_TOL      = 1e-3
MILP_MIP_GAP_BY_NR   = {1: 0.0, 2: 0.05, 3: 0.10}  # mirrors run_experiments.py

# ── Load notebook definitions ────────────────────────────────────────────────
# Cells: 2=imports, 4=OrbitalBody, 5=LambertSolver, 7=asteroid data,
#        9=Parameters, 11=build_index_sets/build_node_mapping, 14=TrajectoryOptimizer,
#        20=build_milp, 22=extract_routes, 23=initialize_mass_ratios, 26=solve_vrtpp_pr
CELL_INDICES = [2, 4, 5, 7, 9, 11, 14, 20, 22, 23, 26]

def _load_notebook_ns():
    nb = json.loads(NOTEBOOK.read_text())
    ns = {"__name__": "__paper_model__"}
    for idx in CELL_INDICES:
        src = "".join(nb["cells"][idx]["source"])
        exec(src, ns)  # noqa: S102
    return ns

print("Loading VRTPP-PaperModel.ipynb definitions...", end=" ", flush=True)
_ns = _load_notebook_ns()
print("OK", flush=True)

OrbitalBody           = _ns["OrbitalBody"]
Parameters            = _ns["Parameters"]
build_index_sets      = _ns["build_index_sets"]
build_node_mapping    = _ns["build_node_mapping"]
solve_vrtpp_pr        = _ns["solve_vrtpp_pr"]

# ── Random instance generator (same as run_experiments.py) ───────────────────
def generate_random_asteroids(n_r: int, n_m: int, seed: int = None):
    rng = random.Random(seed)
    def rb(name):
        return OrbitalBody(
            name=name,
            a=rng.uniform(1.0, 3.0),
            e=rng.uniform(0.0, 0.3),
            i=rng.uniform(0.0, 5.0),
            Omega=rng.uniform(0.0, 360.0),
            omega=rng.uniform(0.0, 360.0),
            M0=rng.uniform(0.0, 360.0),
            epoch=0.0,
        )
    return [rb(f"R{k+1}") for k in range(n_r)], [rb(f"M{k+1}") for k in range(n_m)]

# ── CSV helpers ───────────────────────────────────────────────────────────────
FIELDNAMES = [
    "model", "n_r", "n_m",
    "iterations_min", "iterations_max", "iterations_mean",
    "time_min_sec", "time_max_sec", "time_mean_sec",
    "mining_asteroids_min", "mining_asteroids_max", "mining_asteroids_mean",
    "trivial_problems", "non_converged_problems",
    "mip_gap_final_min", "mip_gap_final_max", "mip_gap_final_mean",
    "notes",
]

def load_csv():
    if not RESULTS_CSV.exists():
        return []
    with open(RESULTS_CSV, newline="") as f:
        return list(csv.DictReader(f))

def save_csv(rows):
    with open(RESULTS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)

def update_csv_row(n_r, n_m, stats):
    rows = load_csv()
    for row in rows:
        if row["model"] == "paper" and int(row["n_r"]) == n_r and int(row["n_m"]) == n_m:
            row["iterations_min"]          = round(stats["iter_min"], 2)
            row["iterations_max"]          = round(stats["iter_max"], 2)
            row["iterations_mean"]         = round(stats["iter_mean"], 2)
            row["time_min_sec"]            = round(stats["time_min"], 2)
            row["time_max_sec"]            = round(stats["time_max"], 2)
            row["time_mean_sec"]           = round(stats["time_mean"], 2)
            row["mining_asteroids_min"]    = round(stats["mine_min"], 2)
            row["mining_asteroids_max"]    = round(stats["mine_max"], 2)
            row["mining_asteroids_mean"]   = round(stats["mine_mean"], 2)
            row["trivial_problems"]        = stats["trivials"]
            row["non_converged_problems"]  = stats["non_convs"]
            row["mip_gap_final_min"]       = round(stats["gap_min"], 4)
            row["mip_gap_final_max"]       = round(stats["gap_max"], 4)
            row["mip_gap_final_mean"]      = round(stats["gap_mean"], 4)
            row["notes"] = (
                f"{N_INSTANCES} random instances seed {BASE_SEED}-"
                f"{BASE_SEED + N_INSTANCES - 1}; "
                f"MIPGap={MILP_MIP_GAP_BY_NR.get(n_r, 0.10)} "
                f"TimeLimit={int(MILP_TIME_LIMIT)}s"
            )
            break
    save_csv(rows)
    print(f"  ✓ results.csv updated for paper n_r={n_r}, n_m={n_m}", flush=True)

# ── Runner ────────────────────────────────────────────────────────────────────
def run_config(n_r, n_m):
    gap = MILP_MIP_GAP_BY_NR.get(n_r, 0.10)
    print(f"\n{'#'*70}\nPAPER CONFIG: n_r={n_r}, n_m={n_m}  MIPGap={gap:.0%}\n{'#'*70}\n", flush=True)
    inst = []
    for idx in range(N_INSTANCES):
        seed = BASE_SEED + idx
        print(f"  Instance {idx+1}/{N_INSTANCES} (seed={seed})...", end=" ", flush=True)
        ref, mine = generate_random_asteroids(n_r, n_m, seed=seed)
        params = Parameters()
        sets   = build_index_sets(params, n_r, n_m)
        n2b, n2n = build_node_mapping(sets, ref, mine)
        try:
            sol = solve_vrtpp_pr(
                params, sets, n2b, n2n,
                max_iterations=MAX_ITERATIONS,
                convergence_tol=CONVERGENCE_TOL,
                time_limit=MILP_TIME_LIMIT,
                mip_gap=gap,
            )
        except Exception as exc:
            print(f"ERROR: {exc}", flush=True)
            inst.append({"iters": MAX_ITERATIONS, "time": 0.0, "mine": 0, "nc": 1, "gap": 0.0})
            continue

        if sol is None:
            print("failed (None)", flush=True)
            inst.append({"iters": MAX_ITERATIONS, "time": 0.0, "mine": 0, "nc": 1, "gap": 0.0})
            continue

        mc  = sum(1 for sr in (sol.get("routes") or []) for n in sr if n in sets["M"])
        nc  = 1 if sol.get("status") not in ("converged",) else 0
        gap = sol.get("mip_gap_final", 0.0)
        inst.append({"iters": sol.get("iterations", MAX_ITERATIONS),
                     "time": sol.get("elapsed_time", 0.0),
                     "mine": mc, "nc": nc, "gap": gap})
        print(f"{sol.get('status')}, {sol.get('iterations')} iters, "
              f"{sol.get('elapsed_time', 0.):.1f}s, {mc} mine, gap={gap:.4f}", flush=True)

    iters = [r["iters"] for r in inst]
    times = [r["time"]  for r in inst]
    mines = [r["mine"]  for r in inst]
    gaps  = [r["gap"]   for r in inst]
    stats = {
        "iter_min": min(iters), "iter_max": max(iters), "iter_mean": statistics.mean(iters),
        "time_min": min(times), "time_max": max(times), "time_mean": statistics.mean(times),
        "mine_min": min(mines), "mine_max": max(mines), "mine_mean": statistics.mean(mines),
        "trivials":  sum(1 for r in inst if r["mine"] == 0),
        "non_convs": sum(r["nc"] for r in inst),
        "gap_min": min(gaps), "gap_max": max(gaps), "gap_mean": statistics.mean(gaps),
    }
    print(f"\n  iter {stats['iter_min']}-{stats['iter_max']} "
          f"(mean {stats['iter_mean']:.1f}) | "
          f"time {stats['time_min']:.1f}-{stats['time_max']:.1f}s "
          f"(mean {stats['time_mean']:.1f}s) | "
          f"mine {stats['mine_min']}-{stats['mine_max']} "
          f"(mean {stats['mine_mean']:.1f}) | "
          f"gap {stats['gap_min']:.4f}-{stats['gap_max']:.4f}", flush=True)
    update_csv_row(n_r, n_m, stats)


def main():
    parser = argparse.ArgumentParser(description="VRTPP-PR paper model scalability experiments")
    parser.add_argument("--config", nargs=2, type=int, metavar=("N_R", "N_M"),
                        help="Run only this single config (e.g. --config 1 4)")
    args = parser.parse_args()

    print(f"\n{'='*70}\nVRTPP-PR Paper Model Experiments\n{'='*70}\n", flush=True)

    rows = load_csv()
    done = {(int(r["n_r"]), int(r["n_m"])) for r in rows
            if r["model"] == "paper" and r.get("iterations_min")}

    if args.config:
        configs_to_run = [tuple(args.config)]
        print(f"Single config mode: n_r={args.config[0]}, n_m={args.config[1]}", flush=True)
        if tuple(args.config) in done:
            print("Config already completed. Re-running.", flush=True)
    else:
        configs_to_run = [(nr, nm) for nr, nm in ALL_CONFIGS if (nr, nm) not in done]
        print(f"Already done: {sorted(done)}")
        print(f"To run:       {configs_to_run}\n", flush=True)

    for n_r, n_m in configs_to_run:
        run_config(n_r, n_m)

    print("\nDone!", flush=True)


if __name__ == "__main__":
    main()
