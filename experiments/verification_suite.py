"""
verification_suite.py — Runs Experiment 1 and Experiment 2 from solution_design.md.

Experiment 1: Arc-Cost Matrix Comparison
  Compare the ΔV matrices produced by baseline (Hohmann seed) vs. proposed
  (TA-grid + distance-corrected T_t) initialization. Uses the paper's canonical
  8-body case study (n_r=2, n_m=5).

Experiment 2: Initialization Sensitivity and Propagation
  Fix the paper's canonical route (Earth → FG3 → Bennu → Earth) and solve
  sequential NLP twice — once with each model's cold-start logic — to show how
  initialization differences propagate across legs.

Outputs written to experiments/results/:
  exp1_dv_heatmap.png
  exp1_summary_table.png
  exp2_timeline.png
  exp2_leg_table.png

Run from the repo root:
    python3 experiments/verification_suite.py
"""

import contextlib, io, json, math, os, pathlib, time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = pathlib.Path(__file__).resolve().parent.parent
NB_PAPER    = ROOT / "VRTPP-PaperModel.ipynb"
NB_PROPOSED = ROOT / "VRTPP_PR_Optimization.ipynb"
RESULTS_DIR = ROOT / "experiments" / "results"

PAPER_CELLS    = [2, 4, 5, 7, 9, 11, 14, 20, 22, 23, 26]
PROPOSED_CELLS = [2, 4, 5, 7, 9, 11, 14, 18, 20, 21, 24]


# ── Namespace loaders ─────────────────────────────────────────────────────────

def _load_namespace(nb_path: pathlib.Path, cell_indices: list, label: str) -> dict:
    print(f"Loading {label} ({nb_path.name})...", flush=True)
    t0 = time.time()
    nb = json.loads(nb_path.read_text())
    ns = {"__name__": f"__{label}__"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for idx in cell_indices:
            src = "".join(nb["cells"][idx]["source"])
            try:
                exec(src, ns)
            except Exception as exc:
                print(f"  WARNING: cell {idx} raised {exc!r}", flush=True)
    print(f"  Loaded in {time.time()-t0:.1f}s", flush=True)
    return ns


def load_paper_namespace() -> dict:
    return _load_namespace(NB_PAPER, PAPER_CELLS, "paper_model")


def load_proposed_namespace() -> dict:
    return _load_namespace(NB_PROPOSED, PROPOSED_CELLS, "proposed_model")


# ── Shared utility ─────────────────────────────────────────────────────────────

def save_figure(fig: plt.Figure, path: pathlib.Path) -> None:
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path.relative_to(ROOT)}", flush=True)


def _mr_to_dv(mr: float, g0: float, I_sp: float) -> float:
    mr = max(1e-10, min(0.999, mr))
    return -g0 * I_sp * math.log(mr)


# ── Experiment 1 ──────────────────────────────────────────────────────────────

def run_experiment_1(ns_paper: dict, ns_proposed: dict) -> dict:
    """Arc-cost matrix comparison (Exp 1 from solution_design.md)."""
    print("\n" + "=" * 70, flush=True)
    print("EXPERIMENT 1: Arc-Cost Matrix Comparison", flush=True)
    print("=" * 70, flush=True)

    # ── Build index sets and node mappings (one per namespace) ────────────────
    def _build(ns):
        params       = ns["Parameters"]()
        sets         = ns["build_index_sets"](params, n_refuel=2, n_mine=5)
        refueling    = [ns["ryugu"], ns["bennu"]]
        mining       = [ns["sg10"], ns["ml"], ns["fg3"], ns["cc21"], ns["anteros"]]
        n2b, n2name  = ns["build_node_mapping"](sets, refueling, mining)
        return params, sets, n2b, n2name

    params_p, sets_p, n2b_p, n2name_p = _build(ns_paper)
    params_o, sets_o, n2b_o, n2name_o = _build(ns_proposed)

    # ── Run initialize_mass_ratios for each model ─────────────────────────────
    print("\nRunning BASELINE initialize_mass_ratios...", flush=True)
    t0 = time.time()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            paper_mr, paper_it = ns_paper["initialize_mass_ratios"](
                params_p, sets_p, n2b_p
            )
    except Exception as exc:
        print(f"  ERROR in paper initialize_mass_ratios: {exc}", flush=True)
        return {}
    print(f"  Done in {time.time()-t0:.1f}s  ({len(paper_mr)} arcs)", flush=True)

    print("Running PROPOSED initialize_mass_ratios...", flush=True)
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(buf):
            proposed_mr, proposed_it, _ = ns_proposed["initialize_mass_ratios"](
                params_o, sets_o, n2b_o
            )
    except Exception as exc:
        print(f"  ERROR in proposed initialize_mass_ratios: {exc}", flush=True)
        return {}
    print(f"  Done in {time.time()-t0:.1f}s  ({len(proposed_mr)} arcs)", flush=True)

    # ── Convert mass ratios to ΔV ─────────────────────────────────────────────
    g0   = params_p.g0
    I_sp = params_p.I_sp

    # Shared arc set (by node pair)
    common_arcs = set(paper_mr.keys()) & set(proposed_mr.keys())
    print(f"\n  Common arc pairs: {len(common_arcs)}", flush=True)

    diffs = []
    arc_data = []
    for (i, j) in common_arcs:
        dv_p = _mr_to_dv(paper_mr[(i, j)],    g0, I_sp)
        dv_o = _mr_to_dv(proposed_mr[(i, j)],  g0, I_sp)
        delta = dv_o - dv_p
        diffs.append(delta)
        arc_data.append({
            "i": i, "j": j,
            "src_name": n2b_p[i].name,
            "dst_name": n2b_p[j].name,
            "dv_paper": dv_p,
            "dv_proposed": dv_o,
            "delta": delta,
        })

    # Metrics
    mean_diff  = float(np.mean(diffs))
    max_diff   = float(np.max(np.abs(diffs)))
    pct_improved = 100.0 * sum(1 for d in diffs if d < 0) / len(diffs)

    # Rank changes: per destination body, compare ordering of sources
    rank_changes = 0
    dst_names = sorted({r["dst_name"] for r in arc_data})
    for dst in dst_names:
        rows = [r for r in arc_data if r["dst_name"] == dst]
        if len(rows) < 2:
            continue
        # Deduplicate by source body name (take min ΔV for virtual copies)
        src_paper    = {}
        src_proposed = {}
        for r in rows:
            sn = r["src_name"]
            src_paper[sn]    = min(src_paper.get(sn, 1e9),    r["dv_paper"])
            src_proposed[sn] = min(src_proposed.get(sn, 1e9), r["dv_proposed"])
        bodies = sorted(src_paper.keys())
        rank_p = sorted(bodies, key=lambda b: src_paper[b])
        rank_o = sorted(bodies, key=lambda b: src_proposed[b])
        for pos, (bp, bo) in enumerate(zip(rank_p, rank_o)):
            if bp != bo:
                rank_changes += 1

    # Canonical route arc diffs (Earth→FG3, FG3→Bennu, Bennu→Earth)
    ROUTE = [("Earth", "1996 FG3"), ("1996 FG3", "101955 Bennu"), ("101955 Bennu", "Earth")]
    route_arc_diffs = []
    for (src, dst) in ROUTE:
        matches = [r for r in arc_data if r["src_name"] == src and r["dst_name"] == dst]
        if matches:
            best = min(matches, key=lambda r: r["dv_paper"])
            route_arc_diffs.append({
                "arc": f"{src} → {dst}",
                "dv_paper": best["dv_paper"],
                "dv_proposed": best["dv_proposed"],
                "delta": best["delta"],
            })
        else:
            route_arc_diffs.append({"arc": f"{src} → {dst}", "dv_paper": None,
                                    "dv_proposed": None, "delta": None})

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n  Mean ΔV diff (proposed − paper): {mean_diff:+.3f} km/s", flush=True)
    print(f"  Max |ΔV diff|:                    {max_diff:.3f} km/s",   flush=True)
    print(f"  % arcs improved (proposed lower): {pct_improved:.1f}%",    flush=True)
    print(f"  Rank changes across destinations: {rank_changes}",          flush=True)
    print("\n  Canonical route arcs:", flush=True)
    for r in route_arc_diffs:
        if r["dv_paper"] is not None:
            print(f"    {r['arc']:35s}  paper={r['dv_paper']:6.2f}  "
                  f"proposed={r['dv_proposed']:6.2f}  Δ={r['delta']:+6.2f} km/s",
                  flush=True)
        else:
            print(f"    {r['arc']:35s}  NOT FOUND", flush=True)

    if pct_improved < 10.0:
        print("  WARNING: proposed improved fewer than 10% of arcs — check initialization",
              flush=True)

    # ── Eccentricity gap: per destination body ────────────────────────────────
    # For each destination, find the best (min ΔV) Earth→body arc for each model.
    # This isolates the effect of destination eccentricity on initialization quality.
    earth_name = "Earth"
    ecc_gap_data = []
    dst_bodies_seen = set()
    for r in arc_data:
        if r["src_name"] != earth_name:
            continue
        dst = r["dst_name"]
        if dst == earth_name or dst in dst_bodies_seen:
            continue
        # Aggregate across all virtual nodes to the same physical body
        matches = [x for x in arc_data if x["src_name"] == earth_name and x["dst_name"] == dst]
        best_paper    = min(matches, key=lambda x: x["dv_paper"])
        best_proposed = min(matches, key=lambda x: x["dv_proposed"])
        # Get eccentricity from node_to_body
        body_j = next(
            (n2b_p[x["j"]] for x in matches if n2b_p[x["j"]].name == dst), None
        )
        if body_j is not None:
            ecc_gap_data.append({
                "body": dst,
                "ecc": body_j.e,
                "dv_paper": best_paper["dv_paper"],
                "dv_proposed": best_proposed["dv_proposed"],
                "gap": best_paper["dv_paper"] - best_proposed["dv_proposed"],
            })
            dst_bodies_seen.add(dst)

    ecc_gap_data.sort(key=lambda x: x["ecc"])
    print("\n  Eccentricity gap (Earth → body, baseline − proposed):", flush=True)
    for row in ecc_gap_data:
        print(f"    {row['body']:25s}  e={row['ecc']:.3f}  "
              f"baseline={row['dv_paper']:6.2f}  proposed={row['dv_proposed']:6.2f}  "
              f"gap={row['gap']:+6.3f} km/s", flush=True)

    # ── Figures ───────────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _plot_exp1_heatmap(arc_data, n2b_p, RESULTS_DIR)
    _plot_exp1_summary_table(
        mean_diff, max_diff, pct_improved, rank_changes, route_arc_diffs, RESULTS_DIR
    )
    _plot_exp1_eccentricity_gap(ecc_gap_data, RESULTS_DIR)

    return {
        "mean_dv_diff": mean_diff,
        "max_dv_diff": max_diff,
        "pct_improved": pct_improved,
        "rank_changes": rank_changes,
        "route_arc_diffs": route_arc_diffs,
        "n_arcs_compared": len(common_arcs),
        "ecc_gap_data": ecc_gap_data,
    }


def _plot_exp1_heatmap(arc_data: list, n2b: dict, results_dir: pathlib.Path) -> None:
    # Deduplicate to physical body pairs, taking min ΔV
    paper_mat, proposed_mat = {}, {}
    for r in arc_data:
        key = (r["src_name"], r["dst_name"])
        paper_mat[key]    = min(paper_mat.get(key, 1e9),    r["dv_paper"])
        proposed_mat[key] = min(proposed_mat.get(key, 1e9), r["dv_proposed"])

    all_bodies = sorted({k[0] for k in paper_mat} | {k[1] for k in paper_mat})
    n = len(all_bodies)
    bidx = {b: i for i, b in enumerate(all_bodies)}

    diff_matrix = np.full((n, n), np.nan)
    for key, dv_p in paper_mat.items():
        dv_o = proposed_mat.get(key, dv_p)
        r, c = bidx[key[0]], bidx[key[1]]
        diff_matrix[r, c] = dv_o - dv_p

    abs_max = np.nanmax(np.abs(diff_matrix))
    abs_max = max(abs_max, 0.1)

    fig, ax = plt.subplots(figsize=(max(8, n), max(6, n - 1)))
    im = ax.imshow(diff_matrix, cmap="RdBu_r", vmin=-abs_max, vmax=abs_max,
                   aspect="auto")
    plt.colorbar(im, ax=ax, label="ΔV diff: proposed − baseline (km/s)")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    short = [b.split()[-1] for b in all_bodies]
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(short, fontsize=8)
    ax.set_xlabel("Destination body")
    ax.set_ylabel("Source body")
    ax.set_title("Exp 1: ΔV Difference — Proposed − Baseline (km/s)\n"
                 "Blue = proposed improved, Red = baseline was better")

    for r in range(n):
        for c in range(n):
            val = diff_matrix[r, c]
            if not np.isnan(val):
                ax.text(c, r, f"{val:+.1f}", ha="center", va="center",
                        fontsize=7, color="black")

    fig.tight_layout()
    save_figure(fig, results_dir / "exp1_dv_heatmap.png")


def _plot_exp1_summary_table(mean_diff, max_diff, pct_improved, rank_changes,
                              route_arc_diffs, results_dir: pathlib.Path) -> None:
    rows = [
        ["Mean ΔV diff (proposed − paper)", f"{mean_diff:+.3f} km/s"],
        ["Max |ΔV diff|",                   f"{max_diff:.3f} km/s"],
        ["% arcs improved",                 f"{pct_improved:.1f}%"],
        ["% arcs where paper was better",   f"{100-pct_improved:.1f}%"],
        ["Rank changes across destinations", str(rank_changes)],
    ]
    for r in route_arc_diffs:
        if r["dv_paper"] is not None:
            rows.append([
                f"Route: {r['arc']}",
                f"paper={r['dv_paper']:.2f}  proposed={r['dv_proposed']:.2f}  "
                f"Δ={r['delta']:+.2f} km/s",
            ])

    fig, ax = plt.subplots(figsize=(10, max(3, 0.4 * len(rows) + 1.5)))
    ax.axis("off")
    col_labels = ["Metric", "Value"]
    table = ax.table(
        cellText=rows,
        colLabels=col_labels,
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width([0, 1])
    # Header styling
    for j in range(2):
        table[(0, j)].set_facecolor("#2c3e50")
        table[(0, j)].set_text_props(color="white", fontweight="bold")
    # Alternating rows
    for i in range(1, len(rows) + 1):
        color = "#ecf0f1" if i % 2 == 0 else "white"
        for j in range(2):
            table[(i, j)].set_facecolor(color)

    ax.set_title("Experiment 1: Arc-Cost Initialization Comparison",
                 fontsize=11, fontweight="bold", pad=12)
    fig.tight_layout()
    save_figure(fig, results_dir / "exp1_summary_table.png")


def _plot_exp1_eccentricity_gap(ecc_gap_data: list, results_dir: pathlib.Path) -> None:
    """Plot ΔV gap (baseline − proposed) for Earth→body arcs vs. destination eccentricity."""
    if not ecc_gap_data:
        return

    eccs = [r["ecc"]    for r in ecc_gap_data]
    gaps = [r["gap"]    for r in ecc_gap_data]
    dvp  = [r["dv_paper"]    for r in ecc_gap_data]
    dvo  = [r["dv_proposed"] for r in ecc_gap_data]
    names = [r["body"].split()[-1] for r in ecc_gap_data]  # short label

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # ── Left: ΔV gap vs eccentricity ──────────────────────────────────────────
    ax = axes[0]
    colors = ["#e74c3c" if g < 0 else "#2ecc71" for g in gaps]
    ax.scatter(eccs, gaps, c=colors, s=120, zorder=3, edgecolors="black", linewidths=0.5)
    for x, y, name in zip(eccs, gaps, names):
        ax.annotate(name, (x, y), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)

    # Fit a linear trend
    if len(eccs) >= 3:
        z = np.polyfit(eccs, gaps, 1)
        xfit = np.linspace(min(eccs), max(eccs), 100)
        ax.plot(xfit, np.polyval(z, xfit), color="#7f8c8d", linewidth=1.5,
                linestyle="--", label=f"trend  slope={z[0]:+.2f} km/s per unit e")
        ax.legend(fontsize=8)

    ax.set_xlabel("Destination body eccentricity (e)", fontsize=10)
    ax.set_ylabel("ΔV gap: baseline − proposed (km/s)", fontsize=10)
    ax.set_title("Eccentricity vs. Initialization Improvement\n"
                 "Green = proposed better, Red = baseline better", fontsize=10)
    ax.grid(linestyle="--", alpha=0.4)

    # ── Right: baseline vs proposed ΔV grouped by body ────────────────────────
    ax2 = axes[1]
    x = np.arange(len(ecc_gap_data))
    width = 0.35
    ax2.bar(x - width/2, dvp, width, label="Baseline", color="#3498db", alpha=0.85,
            edgecolor="black", linewidth=0.5)
    ax2.bar(x + width/2, dvo, width, label="Proposed", color="#e74c3c", alpha=0.85,
            edgecolor="black", linewidth=0.5)

    # Annotate eccentricity above each group
    for xi, row in zip(x, ecc_gap_data):
        ax2.text(xi, max(row["dv_paper"], row["dv_proposed"]) + 0.2,
                 f"e={row['ecc']:.2f}", ha="center", va="bottom", fontsize=7, color="#555")

    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=9)
    ax2.set_ylabel("ΔV for Earth → body (km/s)", fontsize=10)
    ax2.set_xlabel("Destination body (sorted by eccentricity)", fontsize=10)
    ax2.set_title("Earth → Body ΔV: Baseline vs. Proposed\n"
                  "Sorted by destination eccentricity", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("Exp 1b: Eccentricity Handling — Does Proposed Init Improve More for Eccentric Bodies?",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    save_figure(fig, results_dir / "exp1_eccentricity_gap.png")


# ── Experiment 2 ──────────────────────────────────────────────────────────────

def run_experiment_2(ns_paper: dict, ns_proposed: dict) -> dict:
    """Sequential NLP sensitivity and propagation (Exp 2 from solution_design.md)."""
    print("\n" + "=" * 70, flush=True)
    print("EXPERIMENT 2: Initialization Sensitivity and Propagation", flush=True)
    print("=" * 70, flush=True)

    earth_p = ns_paper["earth"]
    fg3_p   = ns_paper["fg3"]
    bennu_p = ns_paper["bennu"]

    earth_o = ns_proposed["earth"]
    fg3_o   = ns_proposed["fg3"]
    bennu_o = ns_proposed["bennu"]

    ROUTE_LABELS = ["Earth → FG3", "FG3 → Bennu", "Bennu → Earth"]

    def _solve_route(traj, bodies):
        """Solve three sequential legs, cold-starting each (T_t_prev=None)."""
        legs = []
        T_arr = 0.0
        for bi, bj in zip(bodies[:-1], bodies[1:]):
            try:
                result = traj.optimize_segment(bi, bj, T_arrival_i=T_arr,
                                               T_t_prev=None, T_d_prev=None)
            except Exception as exc:
                print(f"    WARNING: optimize_segment failed ({exc!r}), using sentinel",
                      flush=True)
                result = {"T_d": T_arr, "T_t": 6.5, "delta_v": 100.0,
                          "T_a": T_arr + 6.5, "mass_ratio": 1e-10}
            legs.append(result)
            T_arr = result["T_a"]
        return legs

    # Baseline
    print("\nRunning BASELINE sequential NLP (paper model)...", flush=True)
    params_p  = ns_paper["Parameters"]()
    paper_traj = ns_paper["TrajectoryOptimizer"](params_p)
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        baseline_legs = _solve_route(paper_traj, [earth_p, fg3_p, bennu_p, earth_p])
    print(f"  Done in {time.time()-t0:.1f}s", flush=True)

    # Proposed
    print("Running PROPOSED sequential NLP (proposed model)...", flush=True)
    params_o   = ns_proposed["Parameters"]()
    proposed_traj = ns_proposed["TrajectoryOptimizer"](params_o)
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        proposed_legs = _solve_route(proposed_traj, [earth_o, fg3_o, bennu_o, earth_o])
    print(f"  Done in {time.time()-t0:.1f}s", flush=True)

    baseline_total  = sum(r["delta_v"] for r in baseline_legs)
    proposed_total  = sum(r["delta_v"] for r in proposed_legs)
    improvement_abs = baseline_total - proposed_total
    improvement_pct = 100.0 * improvement_abs / baseline_total if baseline_total > 0 else 0.0

    # ── Print results ─────────────────────────────────────────────────────────
    print(f"\n  {'Leg':<20}  {'Model':<10} {'T_d':>7} {'T_t':>7} {'ΔV':>8} {'T_arrival':>10}",
          flush=True)
    print(f"  {'-'*20}  {'-'*10} {'-'*7} {'-'*7} {'-'*8} {'-'*10}", flush=True)
    for lbl, b_leg, o_leg in zip(ROUTE_LABELS, baseline_legs, proposed_legs):
        print(f"  {lbl:<20}  {'Baseline':<10} {b_leg['T_d']:7.3f} {b_leg['T_t']:7.3f} "
              f"{b_leg['delta_v']:8.3f} {b_leg['T_a']:10.3f}", flush=True)
        print(f"  {'':20}  {'Proposed':<10} {o_leg['T_d']:7.3f} {o_leg['T_t']:7.3f} "
              f"{o_leg['delta_v']:8.3f} {o_leg['T_a']:10.3f}", flush=True)
    print(f"\n  Total ΔV — Baseline: {baseline_total:.3f} km/s  "
          f"Proposed: {proposed_total:.3f} km/s  "
          f"Improvement: {improvement_abs:+.3f} km/s ({improvement_pct:+.1f}%)", flush=True)

    # Sanity checks
    if proposed_total > baseline_total + 1.0:
        print("  WARNING: proposed total ΔV exceeds baseline by >1 km/s", flush=True)
    for i, (bl, pl) in enumerate(zip(baseline_legs, proposed_legs)):
        if bl["delta_v"] > 50.0:
            print(f"  WARNING: baseline leg {i+1} ΔV={bl['delta_v']:.1f} — NLP may have failed",
                  flush=True)
        if pl["delta_v"] > 50.0:
            print(f"  WARNING: proposed leg {i+1} ΔV={pl['delta_v']:.1f} — NLP may have failed",
                  flush=True)

    # ── Figures ───────────────────────────────────────────────────────────────
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _plot_exp2_timeline(baseline_legs, proposed_legs, ROUTE_LABELS, RESULTS_DIR)
    _plot_exp2_leg_table(baseline_legs, proposed_legs, ROUTE_LABELS,
                         baseline_total, proposed_total, RESULTS_DIR)

    return {
        "baseline_legs": baseline_legs,
        "proposed_legs": proposed_legs,
        "baseline_total_dv": baseline_total,
        "proposed_total_dv": proposed_total,
        "dv_improvement_kms": improvement_abs,
        "dv_improvement_pct": improvement_pct,
    }


def _plot_exp2_timeline(baseline_legs, proposed_legs, labels, results_dir):
    COLORS = ["#3498db", "#e67e22", "#2ecc71"]

    fig, axes = plt.subplots(2, 1, figsize=(12, 5), sharex=True)
    for ax_idx, (ax, legs, model_name) in enumerate(
        [(axes[0], baseline_legs, "Baseline (Hohmann seed)"),
         (axes[1], proposed_legs, "Proposed (TA-grid)")]
    ):
        for k, (leg, lbl, col) in enumerate(zip(legs, labels, COLORS)):
            T_d, T_a, dv = leg["T_d"], leg["T_a"], leg["delta_v"]
            ax.broken_barh([(T_d, T_a - T_d)], (k - 0.3, 0.6),
                           facecolors=col, alpha=0.8, edgecolor="black", linewidth=0.5)
            ax.text((T_d + T_a) / 2, k, f"{dv:.2f} km/s",
                    ha="center", va="center", fontsize=8, fontweight="bold")
        total = sum(l["delta_v"] for l in legs)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_title(f"{model_name}  (total ΔV = {total:.2f} km/s)", fontsize=10)
        ax.set_xlim(left=0)
        ax.grid(axis="x", linestyle="--", alpha=0.4)

    axes[1].set_xlabel("Mission time (TU)", fontsize=10)
    fig.suptitle("Experiment 2: Sequential NLP — Mission Timeline Comparison", fontsize=11)
    fig.tight_layout()
    save_figure(fig, results_dir / "exp2_timeline.png")


def _plot_exp2_leg_table(baseline_legs, proposed_legs, labels,
                         baseline_total, proposed_total, results_dir):
    col_labels = ["Leg", "Model", "T_d (TU)", "T_t (TU)", "ΔV (km/s)", "T_arrival (TU)"]
    rows = []
    for lbl, bl, pl in zip(labels, baseline_legs, proposed_legs):
        rows.append([lbl, "Baseline",
                     f"{bl['T_d']:.3f}", f"{bl['T_t']:.3f}",
                     f"{bl['delta_v']:.3f}", f"{bl['T_a']:.3f}"])
        rows.append(["", "Proposed",
                     f"{pl['T_d']:.3f}", f"{pl['T_t']:.3f}",
                     f"{pl['delta_v']:.3f}", f"{pl['T_a']:.3f}"])
    # Total row
    rows.append(["TOTAL", "Baseline", "", "", f"{baseline_total:.3f}", ""])
    rows.append(["",      "Proposed", "", "", f"{proposed_total:.3f}", ""])

    fig, ax = plt.subplots(figsize=(12, max(3, 0.45 * len(rows) + 1.5)))
    ax.axis("off")
    table = ax.table(cellText=rows, colLabels=col_labels, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width(list(range(len(col_labels))))

    # Header
    for j in range(len(col_labels)):
        table[(0, j)].set_facecolor("#2c3e50")
        table[(0, j)].set_text_props(color="white", fontweight="bold")
    # Baseline rows = light blue, proposed rows = light orange, total rows = light grey
    baseline_color = "#d6eaf8"
    proposed_color = "#fdebd0"
    total_color    = "#d5d8dc"
    for i, row in enumerate(rows, start=1):
        model = row[1]
        color = baseline_color if model == "Baseline" else (
                proposed_color if model == "Proposed" else total_color)
        for j in range(len(col_labels)):
            table[(i, j)].set_facecolor(color)

    ax.set_title("Experiment 2: Per-Leg Trajectory Parameters — Baseline vs. Proposed",
                 fontsize=11, fontweight="bold", pad=12)
    fig.tight_layout()
    save_figure(fig, results_dir / "exp2_leg_table.png")


# ── Summary writer ────────────────────────────────────────────────────────────

def write_summary(results1: dict, results2: dict, results_dir: pathlib.Path) -> None:
    import datetime
    path = results_dir / "results_summary.md"
    r1 = results1
    r2 = results2

    lines = [
        "# Verification Suite Results",
        f"_Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "---",
        "",
        "## Experiment 1: Arc-Cost Matrix Comparison",
        "",
        "Initialization strategy: **Baseline** = single Hohmann seed at T_d=0;  ",
        "**Proposed** = TA-grid (16 true-anomaly samples) + distance-corrected T_t seeds.",
        "",
        "### Summary metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Arcs compared | {r1.get('n_arcs_compared', 'N/A')} |",
        f"| Mean ΔV diff (proposed − paper) | {r1.get('mean_dv_diff', float('nan')):+.3f} km/s |",
        f"| Max |ΔV diff| | {r1.get('max_dv_diff', float('nan')):.3f} km/s |",
        f"| % arcs improved by proposed | {r1.get('pct_improved', float('nan')):.1f}% |",
        f"| % arcs where paper was better | {100 - r1.get('pct_improved', 0):.1f}% |",
        f"| Rank changes across destinations | {r1.get('rank_changes', 'N/A')} |",
        "",
        "### Canonical route arcs (Earth → FG3 → Bennu → Earth)",
        "",
        "| Arc | Baseline ΔV (km/s) | Proposed ΔV (km/s) | Δ (km/s) |",
        "|-----|-------------------|-------------------|----------|",
    ]
    for arc in r1.get("route_arc_diffs", []):
        if arc["dv_paper"] is not None:
            lines.append(
                f"| {arc['arc']} | {arc['dv_paper']:.3f} | {arc['dv_proposed']:.3f} "
                f"| {arc['delta']:+.3f} |"
            )
        else:
            lines.append(f"| {arc['arc']} | N/A | N/A | N/A |")

    lines += [
        "",
        "### Eccentricity gap (Earth → body arcs, sorted by eccentricity)",
        "",
        "| Body | Eccentricity | Baseline ΔV (km/s) | Proposed ΔV (km/s) | Gap (B−P, km/s) |",
        "|------|-------------|-------------------|-------------------|-----------------|",
    ]
    for row in r1.get("ecc_gap_data", []):
        lines.append(
            f"| {row['body']} | {row['ecc']:.3f} | {row['dv_paper']:.3f} "
            f"| {row['dv_proposed']:.3f} | {row['gap']:+.3f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Experiment 2: Initialization Sensitivity and Propagation",
        "",
        "Fixed route: **Earth → 1996 FG3 → 101955 Bennu → Earth** (paper Table 5 route).  ",
        "Each leg is cold-started (T_t_prev=None), invoking each model's own init logic.",
        "",
        "### Per-leg trajectory parameters",
        "",
        "| Leg | Model | T_d (TU) | T_t (TU) | ΔV (km/s) | T_arrival (TU) |",
        "|-----|-------|----------|----------|-----------|----------------|",
    ]
    labels = ["Earth → FG3", "FG3 → Bennu", "Bennu → Earth"]
    for lbl, bl, pl in zip(labels,
                            r2.get("baseline_legs", []),
                            r2.get("proposed_legs", [])):
        lines.append(
            f"| {lbl} | Baseline | {bl['T_d']:.3f} | {bl['T_t']:.3f} "
            f"| {bl['delta_v']:.3f} | {bl['T_a']:.3f} |"
        )
        lines.append(
            f"| | Proposed | {pl['T_d']:.3f} | {pl['T_t']:.3f} "
            f"| {pl['delta_v']:.3f} | {pl['T_a']:.3f} |"
        )

    b_total = r2.get("baseline_total_dv", float("nan"))
    p_total = r2.get("proposed_total_dv", float("nan"))
    imp_abs = r2.get("dv_improvement_kms", float("nan"))
    imp_pct = r2.get("dv_improvement_pct", float("nan"))

    lines += [
        "",
        "### Total route ΔV",
        "",
        f"| Model | Total ΔV (km/s) |",
        f"|-------|----------------|",
        f"| Baseline | {b_total:.3f} |",
        f"| Proposed | {p_total:.3f} |",
        f"| Improvement | {imp_abs:+.3f} km/s ({imp_pct:+.1f}%) |",
        "",
        "---",
        "",
        "## Output files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `exp1_dv_heatmap.png` | Heatmap of ΔV differences (proposed − baseline) per body pair |",
        "| `exp1_summary_table.png` | Summary metrics table for Exp 1 |",
        "| `exp1_eccentricity_gap.png` | ΔV gap vs. destination eccentricity (Exp 1b) |",
        "| `exp2_timeline.png` | Mission timeline comparison (horizontal bar chart) |",
        "| `exp2_leg_table.png` | Per-leg parameter table for Exp 2 |",
        "",
    ]

    path.write_text("\n".join(lines))
    print(f"  Saved: {path.relative_to(ROOT)}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    ns_paper    = load_paper_namespace()
    ns_proposed = load_proposed_namespace()

    results1 = run_experiment_1(ns_paper, ns_proposed)
    results2 = run_experiment_2(ns_paper, ns_proposed)

    write_summary(results1, results2, RESULTS_DIR)

    print("\n" + "=" * 70, flush=True)
    print("VERIFICATION SUITE COMPLETE", flush=True)
    print("=" * 70, flush=True)

    expected = [
        RESULTS_DIR / "exp1_dv_heatmap.png",
        RESULTS_DIR / "exp1_summary_table.png",
        RESULTS_DIR / "exp1_eccentricity_gap.png",
        RESULTS_DIR / "exp2_timeline.png",
        RESULTS_DIR / "exp2_leg_table.png",
        RESULTS_DIR / "results_summary.md",
    ]
    for p in expected:
        status = "OK" if p.exists() else "MISSING"
        print(f"  [{status}] {p.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
