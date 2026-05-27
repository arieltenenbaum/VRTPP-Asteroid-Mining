"""
run_exp1_porkchop.py — Standalone Exp 1 porkchop overlay (no Gurobi needed).

Generates experiments/results/exp1_porkchop_overlay.png:
  Two-panel Δv landscape for Earth→SG10 (e=0.425) and Earth→Bennu (e=0.020)
  with paper seed (T_d=0, T_t_hoh) and TA-grid seed candidates overlaid.

Run from repo root:
    python3 experiments/run_exp1_porkchop.py
"""

import json, os, sys, pathlib
import numpy as np

ROOT    = pathlib.Path(__file__).resolve().parent.parent
NB_PATH = ROOT / 'VRTPP_PR_Optimization.ipynb'
OUT_DIR = ROOT / 'experiments' / 'results'
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Load notebook cell definitions ──────────────────────────────────────────
print("Loading notebook definitions...")
nb = json.loads(NB_PATH.read_text())

# Cells needed: imports(2), OrbitalBody(4), LambertSolver(5),
#               body data(7), Parameters(9), case-study setup(12), TrajectoryOptimizer(14)
CELLS = [2, 4, 5, 7, 9, 11, 12, 14]
ns = {'__name__': '__porkchop__'}
for idx in CELLS:
    src = ''.join(nb['cells'][idx]['source'])
    try:
        exec(compile(src, f'<cell {idx}>', 'exec'), ns)
    except Exception as ex:
        print(f"  Cell {idx} exec error: {ex}")
        sys.exit(1)

print("  Definitions loaded OK")

params         = ns['params']
earth          = ns['earth']
sg10           = ns['sg10']
bennu          = ns['bennu']
TrajectoryOpt  = ns['TrajectoryOptimizer']

_traj = TrajectoryOpt(params)

# ── Plot setup ───────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

body_pairs = [
    (earth, sg10,  'Earth → 2001 SG10\n(e = 0.425, high-eccentricity)',  'a)'),
    (earth, bennu, 'Earth → 101955 Bennu\n(e = 0.020, near-circular)', 'b)'),
]

N_TD, N_TT = 80, 60
T_D_MAX     = 14.0
T_T_LO      = 1.0
T_T_HI      = 16.0
N_TA        = 16

fig, axes = plt.subplots(1, 2, figsize=(15, 6))

for ax, (body_i, body_j, title, lbl) in zip(axes, body_pairs):
    print(f"\nComputing Δv grid for {title.split(chr(10))[0]} ...")

    # ── Δv landscape ──
    td_arr = np.linspace(0.0, T_D_MAX, N_TD)
    tt_arr = np.linspace(T_T_LO, T_T_HI, N_TT)
    TT_d, TT_t = np.meshgrid(td_arr, tt_arr)
    DV = np.full_like(TT_d, np.nan)
    for ii in range(N_TT):
        for jj in range(N_TD):
            try:
                dv = _traj.compute_delta_v(body_i, body_j, TT_d[ii, jj], TT_t[ii, jj])
                DV[ii, jj] = dv if dv < 99.0 else np.nan
            except Exception:
                pass
    print(f"  Grid done. Δv range: {np.nanmin(DV):.2f}–{np.nanpercentile(DV,97):.2f} km/s")

    dv_lo = np.nanmin(DV)
    dv_hi = np.nanpercentile(DV, 97)
    im = ax.pcolormesh(TT_d, TT_t, DV, cmap='viridis', shading='auto',
                       vmin=dv_lo, vmax=dv_hi)
    ax.contour(TT_d, TT_t, DV, levels=np.linspace(dv_lo, dv_hi, 10),
               colors='cyan', linewidths=0.5, alpha=0.45)
    cb = plt.colorbar(im, ax=ax, pad=0.02)
    cb.set_label('Δv [km/s]', fontsize=10)

    # ── Paper seed ──
    T_t_hoh = np.pi * np.sqrt(((body_i.a + body_j.a) / 2.0)**3)
    ax.scatter(0.0, T_t_hoh, marker='X', color='red', s=220, zorder=8,
               linewidths=1.5, edgecolors='white',
               label=f'Paper seed  T_d=0, T_t={T_t_hoh:.2f} TU')

    try:
        paper_dv = _traj.compute_delta_v(body_i, body_j, 0.0, T_t_hoh)
        print(f"  Paper seed Δv: {paper_dv:.2f} km/s  (T_d=0, T_t={T_t_hoh:.2f})")
    except Exception:
        print("  Paper seed Δv: (compute failed)")

    # ── TA-grid seeds ──
    td_cands = []
    for k in range(N_TA):
        nu = k * 2.0 * np.pi / N_TA
        t_cand = body_i.time_at_true_anomaly_after(nu, 0.0)
        if 0.0 <= t_cand <= T_D_MAX:
            td_cands.append(t_cand)
    if not td_cands:
        td_cands = [0.0]

    best_dv, best_td, best_tt = 1e9, 0.0, T_t_hoh
    all_td_s, all_tt_s = [], []

    for td in td_cands:
        r_dep = np.linalg.norm(body_i.position_at_time(td))
        T_t_ecc = np.pi * np.sqrt(((r_dep + body_j.a) / 2.0)**3)
        for tt in [0.5 * T_t_hoh, T_t_hoh, T_t_ecc, 2.0 * T_t_hoh]:
            if T_T_LO <= tt <= T_T_HI:
                try:
                    dv = _traj.compute_delta_v(body_i, body_j, td, tt)
                    if dv < 99.0:
                        all_td_s.append(td)
                        all_tt_s.append(tt)
                        if dv < best_dv:
                            best_dv, best_td, best_tt = dv, td, tt
                except Exception:
                    pass

    print(f"  TA-grid: {len(all_td_s)} seeds evaluated; best Δv={best_dv:.2f} km/s"
          f"  (T_d={best_td:.2f}, T_t={best_tt:.2f})")

    if all_td_s:
        ax.scatter(all_td_s, all_tt_s, marker='.', color='orange', s=35,
                   zorder=5, alpha=0.75,
                   label=f'TA-grid seeds ({len(all_td_s)} evaluated)')
    ax.scatter(best_td, best_tt, marker='*', color='yellow', s=350, zorder=9,
               edgecolors='black', linewidths=0.7,
               label=f'Best TA-grid seed  Δv={best_dv:.1f} km/s')

    ax.set_xlabel('Departure Time T_d [TU]', fontsize=11)
    ax.set_ylabel('Transfer Time T_t [TU]', fontsize=11)
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.legend(loc='upper right', fontsize=8, framealpha=0.82,
              handletextpad=0.4, borderpad=0.4)
    ax.text(0.03, 0.97, lbl, transform=ax.transAxes,
            fontsize=13, fontweight='bold', color='white', va='top', ha='left')

fig.suptitle(
    'Δv Porkchop Landscape: Paper Seed vs TA-Grid Seed Coverage\n'
    'Exp 1 — Orbital geometry and initialization sensitivity (RQ1)',
    fontsize=12, fontweight='bold'
)
plt.tight_layout()
out = OUT_DIR / 'exp1_porkchop_overlay.png'
plt.savefig(str(out), dpi=150, bbox_inches='tight')
print(f"\nSaved: {out}")
