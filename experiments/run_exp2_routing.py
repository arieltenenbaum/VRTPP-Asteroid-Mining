"""
run_exp2_routing.py — Exp 2 MILP-only routing comparison (RQ2).

Isolates the effect of initialization on MILP routing by running the MILP
exactly once with each model's initial mass ratio matrix (no NLP iterations).
Compares which mining asteroids are selected and annotates added/dropped
bodies with their Δv improvement from Exp 1.

Run from repo root:
    python3 experiments/run_exp2_routing.py

Outputs:
    experiments/results/exp2_arc_cost_table.png
    experiments/results/exp2_routing_comparison.png
"""

import json, os, sys, pathlib, warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT      = pathlib.Path(__file__).resolve().parent.parent
NB_TA     = ROOT / 'VRTPP_PR_Optimization.ipynb'    # TA-grid (periapsis-init)
NB_PAPER  = ROOT / 'VRTPP-PaperModel.ipynb'  # Paper model — loaded from main branch below
OUT_DIR   = ROOT / 'experiments' / 'results'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Exp 1 eccentricity data (Earth→body arcs) ────────────────────────────────
# From results_summary.md — used to annotate routing changes
EXP1_DATA = {
    '101955 Bennu':  {'e': 0.020, 'baseline_dv': 9.423,  'proposed_dv': 10.633, 'gap': -1.210},
    '1989 ML':       {'e': 0.137, 'baseline_dv': 10.567, 'proposed_dv': 8.346,  'gap': +2.221},
    '162173 Ryugu':  {'e': 0.191, 'baseline_dv': 5.294,  'proposed_dv': 6.629,  'gap': -1.335},
    '2001 CC21':     {'e': 0.219, 'baseline_dv': 10.480, 'proposed_dv': 5.341,  'gap': +5.140},
    '1943 Anteros':  {'e': 0.256, 'baseline_dv': 6.281,  'proposed_dv': 5.822,  'gap': +0.459},
    '1996 FG3':      {'e': 0.350, 'baseline_dv': 6.609,  'proposed_dv': 6.686,  'gap': -0.077},
    '2001 SG10':     {'e': 0.425, 'baseline_dv': 22.860, 'proposed_dv': 8.521,  'gap': +14.339},
}

# ── Load notebook definitions ────────────────────────────────────────────────
def load_cells(nb_path, cell_indices, extra_ns=None):
    nb  = json.loads(pathlib.Path(nb_path).read_text())
    ns  = {'__name__': '__exp2__'}
    if extra_ns:
        ns.update(extra_ns)
    for idx in cell_indices:
        src = ''.join(nb['cells'][idx]['source'])
        if src.strip():
            exec(compile(src, f'<cell {idx}>', 'exec'), ns)
    return ns

print("Loading TA-grid model definitions (periapsis-init)...")
# cells: imports(2), OrbitalBody(4), LambertSolver(5), bodies(7), params(9),
#        build_index_sets(11), case-study setup(12), TrajectoryOptimizer(14),
#        build_milp(18), extract_routes(20), TA-grid initialize_mass_ratios(21)
ns_ta = load_cells(NB_TA, [2, 4, 5, 7, 9, 11, 12, 14, 18, 20, 21])
print("  OK")

print("Loading paper model initialize_mass_ratios (from main branch)...")
# Always use VRTPP-PaperModel.ipynb from origin/main — canonical per Notebook Sync Policy
import subprocess
result = subprocess.run(
    ['git', 'show', 'origin/main:VRTPP-PaperModel.ipynb'],
    capture_output=True, text=True, cwd=str(ROOT)
)
if result.returncode != 0:
    print(f"ERROR: could not fetch VRTPP-PaperModel.ipynb from origin/main: {result.stderr}")
    sys.exit(1)
nb_paper = json.loads(result.stdout)
print("  Using origin/main:VRTPP-PaperModel.ipynb")
# Reuse TA-grid ns for shared definitions; only override initialize_mass_ratios
paper_init_src = ''.join(nb_paper['cells'][23]['source'])
ns_paper_init = dict(ns_ta)  # copy all TA-grid definitions
exec(compile(paper_init_src, '<paper_init>', 'exec'), ns_paper_init)
# Now ns_paper_init['initialize_mass_ratios'] is the paper version
print("  OK")

params        = ns_ta['params']
sets          = ns_ta['sets']
node_to_body  = ns_ta['node_to_body']
node_to_name  = ns_ta['node_to_name']
build_milp    = ns_ta['build_milp']
extract_routes = ns_ta['extract_routes']

init_ta    = ns_ta['initialize_mass_ratios']
init_paper = ns_paper_init['initialize_mass_ratios']

# ── Compute both mass ratio matrices ────────────────────────────────────────
print("\nComputing TA-grid mass ratios...")
mr_ta, _, _ = init_ta(params, sets, node_to_body)
print("Computing paper mass ratios...")
mr_paper_result = init_paper(params, sets, node_to_body)
# paper model returns (mass_ratios, init_times) — 2-tuple
mr_paper = mr_paper_result[0] if isinstance(mr_paper_result, tuple) else mr_paper_result

# ── Run MILP once with each matrix ──────────────────────────────────────────
import gurobipy as gp
from gurobipy import GRB

def run_milp_once(mass_ratios, label):
    print(f"\n[MILP] Running single solve for: {label}")
    model, variables = build_milp(params, sets, mass_ratios, node_to_name, node_to_body)
    model.setParam('OutputFlag', 0)
    model.setParam('TimeLimit', 60.0)
    model.setParam('MIPGap', 0.0)
    model.optimize()
    if model.SolCount == 0:
        print(f"  No solution found (status {model.Status})")
        return [], None
    routes = extract_routes(variables['x'], sets)
    obj = model.ObjVal
    print(f"  Status={model.Status}, ObjVal={obj:.3f}, Routes={len(routes)}")
    return routes, obj

routes_ta,    obj_ta    = run_milp_once(mr_ta,    'TA-grid (proposed)')
routes_paper, obj_paper = run_milp_once(mr_paper, 'Paper Hohmann seed')

# ── Extract body names from routes ──────────────────────────────────────────
def route_bodies(routes):
    """Return list of unique body names across all spacecraft routes."""
    bodies = []
    for route in routes:
        for node in route:
            name = node_to_name.get(node, '?')
            if 'Earth' not in name and name not in bodies:
                bodies.append(name)
    return bodies

bodies_ta    = route_bodies(routes_ta)
bodies_paper = route_bodies(routes_paper)

print(f"\nTA-grid route bodies:  {bodies_ta}")
print(f"Paper route bodies:    {bodies_paper}")

added   = [b for b in bodies_ta    if b not in bodies_paper]
dropped = [b for b in bodies_paper if b not in bodies_ta]
shared  = [b for b in bodies_ta    if b in bodies_paper]

print(f"\nAdded by TA-grid:      {added}")
print(f"Dropped by TA-grid:    {dropped}")
print(f"Shared:                {shared}")

# ── Route string helpers ────────────────────────────────────────────────────
def route_str(routes):
    if not routes:
        return "(no routes)"
    parts = []
    for route in routes:
        parts.append(' → '.join(node_to_name.get(n,'?') for n in route))
    return '\n'.join(parts)

# ── Figure 1: Arc cost table ─────────────────────────────────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Build table rows: all bodies that appear in either route
all_bodies = list(dict.fromkeys(bodies_ta + bodies_paper))

rows = []
for b in all_bodies:
    e1 = EXP1_DATA.get(b, {})
    in_ta    = '✓' if b in bodies_ta    else '—'
    in_paper = '✓' if b in bodies_paper else '—'
    e_val    = f"{e1.get('e', '?'):.3f}"    if e1 else '?'
    gap      = e1.get('gap', None)
    gap_str  = f"{gap:+.2f}" if gap is not None else '?'
    rows.append([b, e_val, in_paper, in_ta, gap_str])

col_labels = ['Body', 'Eccentricity', 'Paper route', 'TA-grid route', 'Δv gap\n(baseline−proposed, km/s)']

fig1, ax1 = plt.subplots(figsize=(11, max(3, 0.6 * len(rows) + 2)))
ax1.axis('off')

# Color rows: green if TA-grid adds, red if TA-grid drops, grey if shared
row_colors = []
for b, *_ in rows:
    if b in added:
        row_colors.append(['#d4f4d4'] * 5)
    elif b in dropped:
        row_colors.append(['#fdd4d4'] * 5)
    else:
        row_colors.append(['#f0f0f0'] * 5)

tbl = ax1.table(
    cellText=rows,
    colLabels=col_labels,
    cellLoc='center',
    loc='center',
    cellColours=row_colors,
)
tbl.auto_set_font_size(False)
tbl.set_fontsize(10)
tbl.scale(1, 1.5)

green_patch = mpatches.Patch(color='#d4f4d4', label='Added by TA-grid route')
red_patch   = mpatches.Patch(color='#fdd4d4', label='Dropped by TA-grid route')
grey_patch  = mpatches.Patch(color='#f0f0f0', label='In both routes')
ax1.legend(handles=[green_patch, red_patch, grey_patch],
           loc='lower center', bbox_to_anchor=(0.5, -0.02), fontsize=9, ncol=3)

ax1.set_title(
    'Exp 2 — Arc Cost Changes and MILP Routing Decisions\n'
    '(Single MILP solve, no NLP iterations; Δv gap from Exp 1 Earth→body arcs)',
    fontsize=11, fontweight='bold', pad=12
)

out1 = OUT_DIR / 'exp2_arc_cost_table.png'
plt.tight_layout()
plt.savefig(str(out1), dpi=150, bbox_inches='tight')
print(f"\nSaved: {out1}")
plt.close()

# ── Figure 2: Route comparison diagram ──────────────────────────────────────
fig2, axes2 = plt.subplots(1, 2, figsize=(14, 5))

def draw_route(ax, routes, title, obj, color_map):
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title(title, fontsize=12, fontweight='bold')
    if obj is not None:
        ax.text(5, 9.3, f'First-iteration MILP obj = {obj:.2f}',
                ha='center', fontsize=10, style='italic')
    if not routes:
        ax.text(5, 5, 'No solution', ha='center', va='center', fontsize=12, color='red')
        return
    y_start = 8.5
    for sc_i, route in enumerate(routes):
        names = [node_to_name.get(n, '?') for n in route]
        x_positions = np.linspace(1, 9, len(names))
        # Draw nodes
        for xi, name in zip(x_positions, names):
            is_earth = 'Earth' in name
            bg = '#aed6f1' if is_earth else color_map.get(name, '#f9e79f')
            ax.add_patch(mpatches.FancyBboxPatch(
                (xi - 1.1, y_start - 0.35), 2.2, 0.7,
                boxstyle='round,pad=0.05', facecolor=bg,
                edgecolor='black', linewidth=1.2, zorder=3
            ))
            label = name.replace('162173 ', '').replace('101955 ', '').replace('1943 ', '').replace('2001 ', '').replace('1996 ', '').replace('1989 ', '')
            e_info = EXP1_DATA.get(name, {})
            extra = f"\ne={e_info.get('e',''):.3f}" if e_info else ''
            ax.text(xi, y_start, label + extra,
                    ha='center', va='center', fontsize=7.5, fontweight='bold', zorder=4)
        # Draw arrows
        for xi, xi2 in zip(x_positions[:-1], x_positions[1:]):
            ax.annotate('', xy=(xi2 - 1.1, y_start),
                        xytext=(xi + 1.1, y_start),
                        arrowprops=dict(arrowstyle='->', color='#555', lw=1.5), zorder=2)
        y_start -= 2.5

# Color map: green for added bodies (in TA-grid but not paper), red for dropped
color_map_ta    = {b: '#a9dfbf' for b in added}   # green = added
color_map_paper = {b: '#f1948a' for b in dropped}  # red = dropped by paper's perspective

draw_route(axes2[0], routes_paper, 'Paper Model (Hohmann seed)\nFirst-iteration route',
           obj_paper, color_map_paper)
draw_route(axes2[1], routes_ta,    'TA-Grid Model (proposed)\nFirst-iteration route',
           obj_ta, color_map_ta)

# Legend
green_p = mpatches.Patch(color='#a9dfbf', label='Body added by TA-grid (not in paper route)')
red_p   = mpatches.Patch(color='#f1948a', label='Body in paper route only')
blue_p  = mpatches.Patch(color='#aed6f1', label='Earth (depot)')
yel_p   = mpatches.Patch(color='#f9e79f', label='Shared body')
fig2.legend(handles=[green_p, red_p, blue_p, yel_p],
            loc='lower center', ncol=4, fontsize=9, bbox_to_anchor=(0.5, -0.01))

fig2.suptitle(
    'Exp 2 — MILP Routing Decisions from Each Initialization\n'
    '(Δv cost matrix set by init only; no NLP refinement)',
    fontsize=12, fontweight='bold'
)
plt.tight_layout()
out2 = OUT_DIR / 'exp2_routing_comparison.png'
plt.savefig(str(out2), dpi=150, bbox_inches='tight')
print(f"Saved: {out2}")
plt.close()

# ── Console summary ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("EXP 2 SUMMARY")
print("="*60)
print(f"Paper first-iteration MILP obj:   {obj_paper:.3f}" if obj_paper else "Paper: no solution")
print(f"TA-grid first-iteration MILP obj: {obj_ta:.3f}"    if obj_ta    else "TA-grid: no solution")
print(f"\nPaper route bodies:  {bodies_paper}")
print(f"TA-grid route bodies: {bodies_ta}")
print(f"\nAdded by TA-grid: {added}")
for b in added:
    info = EXP1_DATA.get(b, {})
    if info:
        print(f"  {b}: e={info['e']:.3f}, Δv gap={info['gap']:+.2f} km/s")
print(f"\nDropped by TA-grid: {dropped}")
for b in dropped:
    info = EXP1_DATA.get(b, {})
    if info:
        print(f"  {b}: e={info['e']:.3f}, Δv gap={info['gap']:+.2f} km/s")
print("="*60)
