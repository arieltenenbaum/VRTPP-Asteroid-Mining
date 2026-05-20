"""
run_paper_experiments.py – Run VRTPP-PR paper model scalability experiments.

Runs VRTPP-PaperModel.ipynb's solve_vrtpp_pr for each config in CONFIGS,
with N_INSTANCES random asteroid sets per config, and writes results to
experiments/results.csv (paper rows).

Run from the repo root:
    python3 experiments/run_paper_experiments.py

Settings (matching our_model for fair comparison):
    TimeLimit = 30.0 s per MILP call
    MIPGap    = 0.0  (exact, paper-faithful; same as our_model after fix)
    N_INSTANCES = 5
"""

import os, sys, time, csv, statistics, random, json, contextlib, pathlib

ROOT     = pathlib.Path(__file__).resolve().parent.parent
NB_PATH  = ROOT / 'VRTPP-PaperModel.ipynb'
RESULTS  = ROOT / 'experiments' / 'results.csv'

CONFIGS     = [(1,4), (1,6), (1,8), (2,4), (2,6), (2,8)]
N_INSTANCES = 5
BASE_SEED   = 42
TIME_LIMIT  = 30.0
NOTE        = f'{N_INSTANCES} random instances seed {BASE_SEED}-{BASE_SEED+N_INSTANCES-1}; MIPGap=0.0 TimeLimit={int(TIME_LIMIT)}s'

# ── Load notebook definitions ─────────────────────────────────────────────────
print("Loading VRTPP-PaperModel.ipynb...", flush=True)
nb = json.loads(NB_PATH.read_text())
SELECTED_CELLS = [2, 4, 5, 7, 9, 11, 14, 20, 22, 23, 26]
ns = {'__name__': '__paper_model_defs__'}
for idx in SELECTED_CELLS:
    exec(''.join(nb['cells'][idx]['source']), ns)

OrbitalBody      = ns['OrbitalBody']
Parameters       = ns['Parameters']
build_index_sets = ns['build_index_sets']
build_node_mapping = ns['build_node_mapping']
solve_vrtpp_pr   = ns['solve_vrtpp_pr']
print("Notebook loaded.\n", flush=True)


def generate_random_asteroids(n_r, n_m, seed=None):
    rng = random.Random(seed)
    def rb(name):
        return OrbitalBody(name=name, a=rng.uniform(1.0, 3.0), e=rng.uniform(0.0, 0.3),
                           i=rng.uniform(0.0, 5.0), Omega=rng.uniform(0.0, 360.0),
                           omega=rng.uniform(0.0, 360.0), M0=rng.uniform(0.0, 360.0), epoch=0.0)
    return [rb(f'R{k+1}') for k in range(n_r)], [rb(f'M{k+1}') for k in range(n_m)]


def load_csv():
    with open(RESULTS) as f:
        return list(csv.DictReader(f))

def save_csv(rows, fieldnames):
    with open(RESULTS, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def update_csv_row(n_r, n_m, summary):
    rows = load_csv()
    fieldnames = list(rows[0].keys())
    updated = False
    for row in rows:
        if row['model'] == 'paper' and int(row['n_r']) == n_r and int(row['n_m']) == n_m:
            for key, val in summary.items():
                row[key] = str(val)
            updated = True
            break
    if not updated:
        raise RuntimeError(f'No paper row for n_r={n_r}, n_m={n_m}')
    save_csv(rows, fieldnames)
    print(f"  ✓ results.csv updated for paper n_r={n_r}, n_m={n_m}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────
print(f"{'='*70}\nVRTPP-PR Paper Model Experiments\n{'='*70}\n", flush=True)
print(f"Configs: {CONFIGS}")
print(f"N_INSTANCES={N_INSTANCES}, TimeLimit={TIME_LIMIT}s, MIPGap=0.0\n", flush=True)

log_dir = pathlib.Path('/tmp')

for N_R, N_M in CONFIGS:
    log_path = log_dir / f'paper_experiment_nr{N_R}_nm{N_M}.log'
    print(f"\n{'#'*70}\nCONFIG: n_r={N_R}, n_m={N_M}  (log: {log_path})\n{'#'*70}\n", flush=True)

    params = Parameters()
    sets   = build_index_sets(params, n_refuel=N_R, n_mine=N_M)

    results = []
    for instance_idx in range(N_INSTANCES):
        seed = BASE_SEED + instance_idx
        print(f"  Instance {instance_idx+1:02d}/{N_INSTANCES} seed={seed}...", end=' ', flush=True)
        refueling, mining = generate_random_asteroids(N_R, N_M, seed=seed)
        node_to_body, node_to_name = build_node_mapping(sets, refueling, mining)

        t0 = time.time()
        sol = None
        try:
            with log_path.open('a') as lf, contextlib.redirect_stdout(lf):
                lf.write(f'\n{"="*80}\nInstance {instance_idx+1}/{N_INSTANCES}, seed={seed}\n{"="*80}\n')
                sol = solve_vrtpp_pr(
                    params=params, sets=sets,
                    node_to_body=node_to_body, node_to_name=node_to_name,
                    max_iterations=50, convergence_tol=1e-3,
                    time_limit=TIME_LIMIT,
                )
        except Exception as exc:
            with log_path.open('a') as lf:
                lf.write(f'ERROR seed={seed}: {exc!r}\n')

        elapsed = time.time() - t0
        if sol is None:
            rec = {'iterations': 50, 'time': elapsed, 'mining_count': 0,
                   'trivial': 1, 'non_converged': 1, 'status': 'failed', 'mip_gap_final': 0.0}
        else:
            routes = sol.get('routes') or []
            mining_count = sum(1 for route in routes for node in route if node in sets['M'])
            status = sol.get('status', '')
            rec = {
                'iterations': int(sol.get('iterations', 50)),
                'time': float(sol.get('elapsed_time', elapsed)),
                'mining_count': int(mining_count),
                'trivial': 1 if mining_count == 0 else 0,
                'non_converged': 1 if status == 'max_iterations' else 0,
                'status': status,
                'mip_gap_final': float(sol.get('mip_gap_final', 0.0)),
            }
        results.append(rec)
        print(f"{rec['status']}, {rec['iterations']} iters, {rec['time']:.1f}s, "
              f"{rec['mining_count']} mining, gap={rec['mip_gap_final']:.4f}", flush=True)

    iters  = [r['iterations']    for r in results]
    times  = [r['time']          for r in results]
    mines  = [r['mining_count']  for r in results]
    gaps   = [r['mip_gap_final'] for r in results]
    summary = {
        'iterations_min':          min(iters),
        'iterations_max':          max(iters),
        'iterations_mean':         round(statistics.mean(iters), 1),
        'time_min_sec':            round(min(times), 2),
        'time_max_sec':            round(max(times), 2),
        'time_mean_sec':           round(statistics.mean(times), 2),
        'mining_asteroids_min':    min(mines),
        'mining_asteroids_max':    max(mines),
        'mining_asteroids_mean':   round(statistics.mean(mines), 1),
        'trivial_problems':        sum(r['trivial']       for r in results),
        'non_converged_problems':  sum(r['non_converged'] for r in results),
        'mip_gap_final_min':       round(min(gaps), 6),
        'mip_gap_final_max':       round(max(gaps), 6),
        'mip_gap_final_mean':      round(statistics.mean(gaps), 6),
        'notes':                   NOTE,
    }
    print(f"\n  iter {summary['iterations_min']}-{summary['iterations_max']} "
          f"(mean {summary['iterations_mean']}) | "
          f"time {summary['time_min_sec']}-{summary['time_max_sec']}s | "
          f"gap {summary['mip_gap_final_min']:.4f}-{summary['mip_gap_final_max']:.4f} "
          f"(mean {summary['mip_gap_final_mean']:.4f})", flush=True)
    update_csv_row(N_R, N_M, summary)

print("\nAll paper experiments done!", flush=True)
