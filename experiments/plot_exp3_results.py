"""
plot_exp3_results.py — Generate Experiment 3 comparison plots from results.csv.

Reads experiments/results.csv (written by run_experiments.py and
run_paper_experiments.py) and produces three comparison figures:

  exp3_mining_asteroids.png  — mean mining asteroids visited per config
  exp3_runtime.png           — wall-clock time vs. problem size
  exp3_convergence.png       — convergence iterations, trivial, non-converged

Run AFTER both experiment scripts have completed:
    python3 experiments/run_paper_experiments.py
    python3 experiments/run_experiments.py

Then:
    python3 experiments/plot_exp3_results.py

Optional flags:
    --csv PATH      override path to results.csv
    --init-csv      write an empty results.csv skeleton (all rows, no data)
                    required before running run_paper_experiments.py if the file
                    was deleted (it raises RuntimeError if paper rows are absent)

Outputs written to experiments/results/.
"""

import argparse, csv, math, os, pathlib, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT        = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "experiments" / "results.csv"
RESULTS_DIR = ROOT / "experiments" / "results"

PAPER_CONFIGS    = [(1, 4), (1, 6), (1, 8), (2, 4), (2, 6), (2, 8)]
PROPOSED_CONFIGS = [(1, 4), (1, 6), (1, 8), (2, 4), (2, 6), (2, 8),
                    (3, 4), (3, 6), (3, 8)]
SHARED_CONFIGS   = PAPER_CONFIGS  # subset present in both models

HEADER = (
    "model,n_r,n_m,"
    "iterations_min,iterations_max,iterations_mean,"
    "time_min_sec,time_max_sec,time_mean_sec,"
    "mining_asteroids_min,mining_asteroids_max,mining_asteroids_mean,"
    "trivial_problems,non_converged_problems,"
    "mip_gap_final_min,mip_gap_final_max,mip_gap_final_mean,"
    "notes\n"
)

NUMERIC_COLS = [
    "n_r", "n_m",
    "iterations_min", "iterations_max", "iterations_mean",
    "time_min_sec", "time_max_sec", "time_mean_sec",
    "mining_asteroids_min", "mining_asteroids_max", "mining_asteroids_mean",
    "trivial_problems", "non_converged_problems",
    "mip_gap_final_min", "mip_gap_final_max", "mip_gap_final_mean",
]


# ── CSV helpers ────────────────────────────────────────────────────────────────

def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def load_results(csv_path: pathlib.Path):
    """Return (paper_rows, proposed_rows) as lists of dicts with typed numerics."""
    if not csv_path.exists():
        return [], []

    paper_rows, proposed_rows = [], []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col in NUMERIC_COLS:
                if col in row:
                    row[col] = _safe_float(row[col])
            if row.get("model") == "paper":
                paper_rows.append(row)
            elif row.get("model") in ("our_model", "proposed"):
                proposed_rows.append(row)
    return paper_rows, proposed_rows


def init_csv(csv_path: pathlib.Path) -> None:
    """Write an empty skeleton CSV with all expected rows and no numeric data."""
    NOTE = "skeleton — not yet run"
    with open(csv_path, "w", newline="") as f:
        f.write(HEADER)
        for n_r, n_m in PAPER_CONFIGS:
            f.write(f"paper,{n_r},{n_m},,,,,,,,,,,,,,,,{NOTE}\n")
        for n_r, n_m in PROPOSED_CONFIGS:
            f.write(f"our_model,{n_r},{n_m},,,,,,,,,,,,,,,,{NOTE}\n")
    print(f"Wrote empty skeleton to {csv_path}", flush=True)


# ── Validation ────────────────────────────────────────────────────────────────

def validate_results(paper_rows, proposed_rows):
    warnings = []

    def _check(rows, model_name):
        if len(rows) < 3:
            warnings.append(
                f"{model_name}: only {len(rows)} rows — Experiment 3 may not have run yet"
            )
        empty_configs = []
        for row in rows:
            nr, nm = int(row.get("n_r", 0) or 0), int(row.get("n_m", 0) or 0)
            if row.get("iterations_mean") is None:
                empty_configs.append(f"n_r={nr},n_m={nm}")
        if empty_configs:
            warnings.append(
                f"{model_name}: empty data for configs: {', '.join(empty_configs)}"
            )
        stale = [row for row in rows
                 if "MIPGap=0.03" in (row.get("notes") or "")]
        if stale:
            warnings.append(
                f"{model_name}: {len(stale)} rows have stale MIPGap=0.03 setting — "
                "clear and rerun for fair comparison"
            )

    _check(paper_rows, "paper")
    _check(proposed_rows, "our_model")

    return warnings


# ── Config label helper ────────────────────────────────────────────────────────

def _label(n_r, n_m):
    return f"n_r={n_r}\nn_m={n_m}"


def _sort_key(row):
    return (int(row["n_m"] or 0), int(row["n_r"] or 0))


# ── Plots ─────────────────────────────────────────────────────────────────────

def _save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path.relative_to(ROOT)}", flush=True)


def plot_mining_asteroids_comparison(paper_rows, proposed_rows, results_dir):
    # Filter to shared configs with valid data
    def _pick(rows, configs):
        out = {}
        for row in rows:
            key = (int(row["n_r"] or 0), int(row["n_m"] or 0))
            if key in configs and row.get("mining_asteroids_mean") is not None:
                out[key] = row
        return out

    p_data = _pick(paper_rows,    SHARED_CONFIGS)
    o_data = _pick(proposed_rows, SHARED_CONFIGS)

    configs = sorted((c for c in SHARED_CONFIGS if c in p_data or c in o_data),
                     key=lambda c: (c[1], c[0]))
    if not configs:
        print("  SKIP mining plot — no valid shared data", flush=True)
        return

    x = np.arange(len(configs))
    width = 0.35
    fig, ax = plt.subplots(figsize=(max(8, len(configs) * 1.4), 5))

    def _bar(data_dict, offset, color, label):
        means = [data_dict[c]["mining_asteroids_mean"] if c in data_dict else None
                 for c in configs]
        lows  = [data_dict[c]["mining_asteroids_min"]  if c in data_dict else None
                 for c in configs]
        highs = [data_dict[c]["mining_asteroids_max"]  if c in data_dict else None
                 for c in configs]
        for i, (m, lo, hi) in enumerate(zip(means, lows, highs)):
            if m is not None:
                err_lo = m - lo if lo is not None else 0
                err_hi = hi - m if hi is not None else 0
                ax.bar(x[i] + offset, m, width, color=color, alpha=0.85,
                       edgecolor="black", linewidth=0.5, label=label if i == 0 else "")
                ax.errorbar(x[i] + offset, m, yerr=[[err_lo], [err_hi]],
                            fmt="none", ecolor="black", capsize=3, linewidth=1)

    _bar(p_data, -width / 2, "#3498db", "Baseline (paper)")
    _bar(o_data,  width / 2, "#e74c3c", "Proposed")

    ax.set_xticks(x)
    ax.set_xticklabels([_label(*c) for c in configs], fontsize=9)
    ax.set_ylabel("Mean Mining Asteroids Visited")
    ax.set_xlabel("Problem Configuration")
    ax.set_title("Exp 3: Mining Asteroids Visited — Baseline vs. Proposed\n"
                 "(error bars = min/max across 5 instances)")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    _save(fig, results_dir / "exp3_mining_asteroids.png")


def plot_runtime_vs_problem_size(paper_rows, proposed_rows, results_dir):
    def _pick(rows, configs):
        out = {}
        for row in rows:
            key = (int(row["n_r"] or 0), int(row["n_m"] or 0))
            if key in configs and row.get("time_mean_sec") is not None:
                out[key] = row
        return out

    p_data = _pick(paper_rows,    SHARED_CONFIGS)
    o_data = _pick(proposed_rows, SHARED_CONFIGS)

    configs = sorted((c for c in SHARED_CONFIGS if c in p_data or c in o_data),
                     key=lambda c: (c[1], c[0]))
    if not configs:
        print("  SKIP runtime plot — no valid shared data", flush=True)
        return

    x = np.arange(len(configs))
    fig, ax = plt.subplots(figsize=(max(8, len(configs) * 1.4), 5))

    for data_dict, color, label in [
        (p_data, "#3498db", "Baseline (paper)"),
        (o_data, "#e74c3c", "Proposed"),
    ]:
        means = [data_dict[c]["time_mean_sec"] if c in data_dict else None for c in configs]
        lows  = [data_dict[c]["time_min_sec"]  if c in data_dict else None for c in configs]
        highs = [data_dict[c]["time_max_sec"]  if c in data_dict else None for c in configs]
        valid = [(xi, m, lo, hi) for xi, (m, lo, hi) in enumerate(zip(means, lows, highs))
                 if m is not None]
        if not valid:
            continue
        xi_vals, m_vals, lo_vals, hi_vals = zip(*valid)
        ax.plot(xi_vals, m_vals, "o-", color=color, label=label, linewidth=2, markersize=6)
        ax.fill_between(xi_vals, lo_vals, hi_vals, color=color, alpha=0.15)

    # Log scale if range > 10×
    all_vals = [r["time_mean_sec"] for rows in [p_data.values(), o_data.values()]
                for r in rows if r.get("time_mean_sec")]
    if all_vals and max(all_vals) / max(min(all_vals), 1e-9) > 10:
        ax.set_yscale("log")
        ax.set_ylabel("Wall Time (s) [log scale]")
    else:
        ax.set_ylabel("Wall Time (s)")

    ax.set_xticks(x)
    ax.set_xticklabels([_label(*c) for c in configs], fontsize=9)
    ax.set_xlabel("Problem Configuration")
    ax.set_title("Exp 3: Runtime vs. Problem Size\n"
                 "(shaded band = min/max across 5 instances)")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.4)
    fig.tight_layout()
    _save(fig, results_dir / "exp3_runtime.png")


def plot_convergence_behavior(paper_rows, proposed_rows, results_dir):
    def _pick(rows, configs):
        out = {}
        for row in rows:
            key = (int(row["n_r"] or 0), int(row["n_m"] or 0))
            if key in configs:
                out[key] = row
        return out

    p_data = _pick(paper_rows,    SHARED_CONFIGS)
    o_data = _pick(proposed_rows, SHARED_CONFIGS)

    configs = sorted((c for c in SHARED_CONFIGS if c in p_data or c in o_data),
                     key=lambda c: (c[1], c[0]))
    if not configs:
        print("  SKIP convergence plot — no valid shared data", flush=True)
        return

    # Decide whether to show MIPGap panel
    has_gap = sum(
        1 for rows in [p_data.values(), o_data.values()]
        for r in rows
        if r.get("mip_gap_final_mean") is not None
    )
    n_panels = 4 if has_gap >= len(configs) else 3

    x = np.arange(len(configs))
    width = 0.35
    fig, axes = plt.subplots(1, n_panels, figsize=(4 * n_panels, 5), sharey=False)

    panel_specs = [
        ("iterations_mean",       "Mean Iterations to Convergence"),
        ("trivial_problems",      "Trivial Solutions (0 mining)"),
        ("non_converged_problems","Non-Converged Problems"),
    ]
    if n_panels == 4:
        panel_specs.append(("mip_gap_final_mean", "Mean Final MIP Gap"))

    for ax, (col, ylabel) in zip(axes, panel_specs):
        for i, cfg in enumerate(configs):
            for offset, data_dict, color, model_label in [
                (-width / 2, p_data, "#3498db", "Baseline"),
                ( width / 2, o_data, "#e74c3c", "Proposed"),
            ]:
                val = data_dict.get(cfg, {}).get(col)
                if val is not None:
                    ax.bar(x[i] + offset, val, width, color=color, alpha=0.85,
                           edgecolor="black", linewidth=0.5,
                           label=model_label if i == 0 else "")

        ax.set_xticks(x)
        ax.set_xticklabels([_label(*c) for c in configs], fontsize=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        handles, _ = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=8)

    fig.suptitle("Exp 3: Convergence Behavior — Baseline vs. Proposed\n"
                 "(5 random instances per config)", fontsize=11)
    fig.tight_layout()
    _save(fig, results_dir / "exp3_convergence.png")


# ── Text comparison table ─────────────────────────────────────────────────────

def print_comparison_table(paper_rows, proposed_rows):
    def _idx(rows):
        return {(int(r["n_r"] or 0), int(r["n_m"] or 0)): r for r in rows}

    p = _idx(paper_rows)
    o = _idx(proposed_rows)

    def _fmt(val, fmt=".1f"):
        if val is None:
            return "N/A"
        return format(float(val), fmt)

    header = (f"{'n_r':>4} {'n_m':>4} | "
              f"{'Iter (P/O)':>14} | "
              f"{'Time s (P/O)':>16} | "
              f"{'Mining (P/O)':>14} | "
              f"{'Trivial (P/O)':>14} | "
              f"{'Non-conv (P/O)':>16}")
    print("\n" + "=" * len(header), flush=True)
    print("EXPERIMENT 3: COMPARISON TABLE", flush=True)
    print("=" * len(header), flush=True)
    print(header, flush=True)
    print("-" * len(header), flush=True)

    all_configs = sorted(set(p.keys()) | set(o.keys()), key=lambda c: (c[1], c[0]))
    for cfg in all_configs:
        pr, or_ = p.get(cfg), o.get(cfg)
        iter_p  = _fmt(pr["iterations_mean"] if pr else None)
        iter_o  = _fmt(or_["iterations_mean"] if or_ else None)
        time_p  = _fmt(pr["time_mean_sec"] if pr else None)
        time_o  = _fmt(or_["time_mean_sec"] if or_ else None)
        mine_p  = _fmt(pr["mining_asteroids_mean"] if pr else None)
        mine_o  = _fmt(or_["mining_asteroids_mean"] if or_ else None)
        triv_p  = _fmt(pr["trivial_problems"] if pr else None, ".0f")
        triv_o  = _fmt(or_["trivial_problems"] if or_ else None, ".0f")
        ncon_p  = _fmt(pr["non_converged_problems"] if pr else None, ".0f")
        ncon_o  = _fmt(or_["non_converged_problems"] if or_ else None, ".0f")
        print(
            f"{cfg[0]:>4} {cfg[1]:>4} | "
            f"{iter_p:>6}/{iter_o:<6} | "
            f"{time_p:>7}/{time_o:<7} | "
            f"{mine_p:>6}/{mine_o:<6} | "
            f"{triv_p:>6}/{triv_o:<6} | "
            f"{ncon_p:>7}/{ncon_o:<7}",
            flush=True,
        )
    print("=" * len(header), flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=str(DEFAULT_CSV),
                        help="Path to results.csv")
    parser.add_argument("--init-csv", action="store_true",
                        help="Write empty skeleton CSV and exit")
    args = parser.parse_args()

    csv_path = pathlib.Path(args.csv)

    if args.init_csv:
        init_csv(csv_path)
        return

    paper_rows, proposed_rows = load_results(csv_path)
    print(f"Loaded {len(paper_rows)} paper rows and {len(proposed_rows)} our_model rows "
          f"from {csv_path.relative_to(ROOT)}", flush=True)

    warnings = validate_results(paper_rows, proposed_rows)
    if warnings:
        print("\nWARNINGS:", flush=True)
        for w in warnings:
            print(f"  - {w}", flush=True)
    else:
        print("Validation: OK — no warnings", flush=True)

    if not paper_rows and not proposed_rows:
        print("\nNo data found. Run experiment scripts first, or use --init-csv to "
              "create the skeleton.", flush=True)
        sys.exit(1)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for fn, args_ in [
        (plot_mining_asteroids_comparison, (paper_rows, proposed_rows, RESULTS_DIR)),
        (plot_runtime_vs_problem_size,     (paper_rows, proposed_rows, RESULTS_DIR)),
        (plot_convergence_behavior,        (paper_rows, proposed_rows, RESULTS_DIR)),
    ]:
        try:
            fn(*args_)
        except Exception as exc:
            print(f"  ERROR in {fn.__name__}: {exc}", flush=True)

    print_comparison_table(paper_rows, proposed_rows)

    print("\nDone. Figures in experiments/results/", flush=True)


if __name__ == "__main__":
    main()
