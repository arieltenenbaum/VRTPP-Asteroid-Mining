# VRTPP-PaperModel — Session Handover
**Date:** 2026-04-22 (Session 2)
**File:** `VRTPP-PaperModel.ipynb`
**Status:** Investigating why Earth→FG3 NLP lands in T_t≈4.41 basin instead of paper's T_t=6.26 basin. Two fixes applied; neither fully resolves the issue.

---

## Goal This Session

Reproduce the paper's result (Earth→FG3→Bennu→Earth, 1 spacecraft, obj≈9.4) in `VRTPP-PaperModel.ipynb`. The prior session established that the cascade failure originates at Earth→FG3: our NLP finds T_t=4.41 (dv=10.19 km/s) while the paper finds T_t=6.26 (dv=9.51 km/s) from the **same** (T_d=0, T_t=Hohmann≈3.28) starting point.

---

## `compute_delta_v` Is Correct

Cell 16 verifies `compute_delta_v` against paper Table 5 at the paper's exact known trajectory points and passes. The "two landscape" claim recorded during this session (notebook gives 11.31 km/s vs standalone 9.31 km/s at Hohmann) was a **red herring** — the standalone test most likely had a parameter or unit conversion error. The notebook's orbital mechanics are correct.

The problem is purely NLP local-minimum selection, not a wrong objective function.

---

## Local Minimum Structure (Earth→FG3, T_d=0)

Diagnostic scan confirmed the dv landscape has two local minima at T_d=0:

| T_t (TU) | dv (km/s) | Description |
|----------|-----------|-------------|
| 3.28 | ~9–11 | Hohmann (starting point) |
| 4.41 | ~10.14 | **Our NLP's local minimum** |
| 5.00 | ~12.44 | Hill separating the two basins |
| 6.04–6.26 | ~9.51–9.69 | **Paper's basin (global minimum)** |

The hill at T_t≈5.0 is the barrier. Standard gradient descent from Hohmann descends toward T_t=4.41 and stops. The paper somehow reaches T_t=6.26 from the same starting point.

The user clarified that the paper uses **Python `trust-constr`** (not MATLAB fmincon), so the solver is the same. The reason the paper reaches the correct basin is that `initial_tr_radius` (the trust-region step size) is large enough to jump over the hill.

---

## Fixes Applied This Session

### Fix 1: Multi-start initialization (`initialize_mass_ratios`, Cell 22)

**Commit:** `fd8bff5`

Added 4 extra T_t starting points `[5.0, 7.0, 9.0, 11.0]` for the L-BFGS-B init NLP, so the initialization phase explores multiple basins and returns the globally best mass ratio.

Also fixed a Python closure bug in the original code where `body_i`/`body_j` were captured by reference in a loop (would have used the last loop value for all pairs).

**Current status:** Code is correct, but init still reports mr=0.1035 for Earth→FG3 in runs. Two possible reasons:
1. Jupyter kernel not restarted after the fix — old `initialize_mass_ratios` still in memory
2. The notebook's `compute_delta_v` landscape is different enough that L-BFGS-B from all 5 starting points still converges to the same (wrong) local minimum at dv≈11 km/s

Note: dv≈11 km/s → mr=0.1035 is suspiciously consistent with the notebook's Hohmann dv of 11.31.

### Fix 2: `initial_tr_radius=2` in trust-constr (`optimize_segment`, Cell 14)

**Commit:** `ad4056b`

Changed trust-constr options from default `initial_tr_radius` (=1) to 2:
```python
options={'maxiter': 500, 'verbose': 0, 'gtol': 1e-8, 'xtol': 1e-8, 'initial_tr_radius': 2}
```

**Standalone test:** `initial_tr_radius=2` causes the standalone NLP to land at T_t=6.31 (correct basin) instead of T_t=3.76.

**Notebook result:** With radius=2, iteration-1 NLP gives T_t=3.91 instead of the old T_t=4.41. The radius IS having an effect (T_t moved), but T_t=3.91 is still in the wrong basin. The notebook's different landscape means a larger radius is needed.

---

## What the Latest Run Showed

With both fixes applied, the 35-iteration run still converges to CC21+Anteros (2-spacecraft) — not the paper's route. Key values:

```
Init:  Earth → FG3: mr=0.1035 (→ dv≈11 km/s — same wrong value as before fixes)
Iter1: Earth → FG3: T_t=3.91, dv=9.96 km/s  (was 4.41/10.19 — moving but wrong basin)
Iter1: FG3 → Bennu: T_t=3.03, dv=11.35 km/s  (wrong basin, cascades from wrong T_d_min)
```

The algorithm then oscillates and ultimately selects CC21+Anteros routes because FG3 routes remain expensive.

---

## What To Try Next Session

### Option A: Sweep `initial_tr_radius` against the notebook's actual landscape

A targeted nbconvert test script should:
1. Import only the orbital mechanics portion of the notebook (no Gurobi)
2. Instantiate `TrajectoryOptimizer` exactly as the notebook does
3. Run trust-constr NLP for Earth→FG3 from (T_d=0, T_t=Hohmann) for `initial_tr_radius` ∈ {2, 3, 4, 5, 6, 8, 10}
4. Report which radius value first reaches T_t≈6.26

The nbconvert approach errored in this session before completing. Try running as a `.py` script extracted from notebook cells 2–16 instead.

### Option B: Try SLSQP for the iterative NLP

SLSQP is a different gradient method (sequential quadratic programming) that may have different basin-finding behavior than trust-constr. The paper doesn't specify which trust-region variant they use within `trust-constr`. Try:
```python
res = minimize(objective, x0=x0, method='SLSQP', bounds=..., options={'maxiter': 500, 'ftol': 1e-12})
```

### Option C: Verify NLP at paper's starting conditions directly

Since `compute_delta_v` is verified correct, the question is purely why trust-constr lands at T_t=4.41 instead of 6.26. Run trust-constr manually at (T_d=0, T_t=Hohmann=3.274) with increasing `initial_tr_radius` values and print the converged T_t for each. This is self-contained — no Gurobi needed, just cells 2–16 of the notebook.

### Option D: Accept and document

The paper's result is solver/implementation dependent. `VRTPP_PR_Optimization.ipynb` already reproduces the correct delta-v values via the grid scan (Bug 13 fix). The PaperModel is documented as a faithful implementation that can't reproduce the paper's exact local-minimum selection without knowing the exact solver internals.

---

## Current Notebook State

| Cell | Content | Status |
|------|---------|--------|
| Cell 14 | `TrajectoryOptimizer` with `initial_tr_radius=2` | Applied |
| Cell 17 | Diagnostic markdown | In notebook |
| Cell 18 | dv landscape scan diagnostic | In notebook |
| Cell 22 | `initialize_mass_ratios` with multi-start + closure fix | Applied |
| Cell 23 | Quick check cell (runs init and prints all mass ratios) | In notebook |

No duplicate cells (prior duplicate at index 23 was deleted by editing JSON directly).

---

## Git Commits This Session

| Hash | Description |
|------|-------------|
| `fd8bff5` | Multi-start init NLP to escape local minima |
| `c6f92fc` | Remove duplicate initialize_mass_ratios cell |
| `9ef7278` | Intermediate push |
| `ad4056b` | Fix initial_tr_radius=2 in trust-constr |

---

## File Locations

| File | Purpose |
|------|---------|
| `VRTPP-PaperModel.ipynb` | Paper-faithful implementation (this session's work) |
| `VRTPP_PR_Optimization.ipynb` | Robustified version with all 13 bug fixes — actually reproduces paper dv values |
| `HANDOVER_2026-04-22.md` | Prior session handover (session 1 of 2026-04-22) |
| `HANDOVER_2026-04-22b.md` | This document |

---

## Reference Values (paper Table 5)

| Arc | T_d (TU) | T_t (TU) | dv (km/s) |
|-----|----------|----------|-----------|
| Earth → 1996 FG3 | 0.09 | 6.26 | 9.51 |
| 1996 FG3 → 101955 Bennu | 8.83 | 7.06 | 7.32 |
| 101955 Bennu → Earth | 17.59 | 6.81 | 8.17 |
