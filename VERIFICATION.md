# Optimizer Verification Results

Section 14 of `VRTPP_PR_Optimization.ipynb` runs five independent checks to determine whether the MILP-NLP solver is finding genuinely optimal routes. This document explains what each check does, what the results mean, and what action (if any) is needed.

---

## 14.1 Kepler Equation Residual Check

**What it checks:** After `_solve_kepler` returns an eccentric anomaly `E`, we verify that it actually satisfies Kepler's equation: `|E - e·sin(E) - M| < 1e-8` for all 9 bodies across 24 sampled mean anomalies.

**Result: PASS**

All bodies converge to residuals at machine precision (< 1e-15). The orbital position and velocity calculations fed into the Lambert solver are numerically correct.

---

## 14.2 MILP Optimality Gap

**What it checks:** After the iterative solver converges, we re-solve the MILP with the final mass ratios and read Gurobi's `MIPGap` — the relative difference between the best integer solution found and the LP relaxation lower bound. A gap < 0.01% means Gurobi has mathematically proven no better integer route exists for these mass ratios.

**Result: WARNING — gap = 2.99%**

```
Objective value : 18.917
Best LP bound   : 19.483
MIP gap         : 2.99e-02
```

Gurobi found 10 feasible integer solutions but could not close the gap to zero. This does **not** mean the route is wrong — it means the mass ratios passed to the MILP are imprecise enough that the LP relaxation bound is loose. The 3% gap is a downstream symptom of the NLP local-minimum problem identified in check 14.3: if the NLP produces inflated ΔV estimates for some arcs, the MILP's continuous relaxation overestimates what's achievable and the gap widens.

**Action needed:** Fix the NLP initialization (see 14.3 below). Once the NLP converges to the correct basins, the mass ratios will be accurate and the MILP gap should close.

---

## 14.3 Pork Chop: NLP vs Grid-Search Global Minimum

**What it checks:** For each leg in the final route, we compute a full ΔV grid over (T_d, T_t) and find its global minimum. We then overlay both the NLP's chosen point (red ×) and the grid minimum (white ★) on the pork chop contour plot. If they coincide, the NLP found the global minimum for that leg. If they are far apart, the NLP is stuck in a local basin.

**Result: Two legs have significant local-minimum errors**

| Leg | NLP ΔV | Grid min ΔV | Gap |
|---|---|---|---|
| Earth → 1943 Anteros | 7.88 km/s | 5.84 km/s | **+2.04 km/s** |
| 1943 Anteros → 101955 Bennu | 9.30 km/s | 9.30 km/s | matched |
| 101955 Bennu → 1989 ML | 6.10 km/s | 6.10 km/s | matched |
| 1989 ML → Earth | 8.37 km/s | 4.52 km/s | **+3.84 km/s** |

On the Earth → Anteros leg the NLP converges near (T_d ≈ 1 TU, T_t ≈ 2 TU), which is a shallow local basin in the early part of the pork chop. The true global minimum sits in a deeper basin near (T_d ≈ 2 TU, T_t ≈ 7 TU). On the 1989 ML → Earth leg the NLP overshoots to a high-ΔV region when the global minimum is near (T_d ≈ 34 TU, T_t ≈ 5 TU).

**Root cause:** The coarse grid in `initialize_mass_ratios` scans T_t only up to 13 TU in steps of 2 TU. This is too coarse and too narrow to reliably identify the correct basin before the NLP refines. The NLP warm-start lands in the wrong valley and the Newton-step solver cannot escape.

**Action needed:** In `initialize_mass_ratios`, widen the T_t scan to at least 20 TU and pass the grid-minimum (T_d, T_t) directly as the NLP warm-start rather than a fixed heuristic guess.

---

## 14.4 Brute-Force Route Enumeration (2-Asteroid Subset)

**What it checks:** For a single spacecraft visiting exactly 2 of the 5 mining asteroids, there are only 20 ordered sequences (5 × 4 permutations). We compute total ΔV for all 20 routes using the NLP and check whether the MILP-NLP solution matches the brute-force winner.

**Result: Skipped (route has 4 bodies)**

The MILP chose a 4-body route (Earth → Anteros → Bennu → ML → Earth), so there is no directly comparable 2-body route to validate against. The brute-force table is still useful as a reference: the cheapest 2-body route is Earth → Anteros → SG10 → Earth at 23.9 km/s total.

```
Earth -> 1943 Anteros -> 2001 SG10 -> Earth     23.934 km/s  ← cheapest 2-body
Earth -> 2001 CC21    -> 1989 ML   -> Earth     24.468 km/s
Earth -> 1943 Anteros -> 2001 CC21 -> Earth     25.450 km/s
...
Earth -> 2001 SG10    -> 1996 FG3  -> Earth     44.076 km/s  ← most expensive
```

When the NLP initialization is fixed and a 2-body run is attempted, re-run this check to confirm the MILP picks the 23.9 km/s winner.

---

## 14.5 Perturbation Sensitivity Test

**What it checks:** For each leg in the final route, we nudge the departure time by ±0.1 TU and ±0.5 TU (holding T_t fixed) and verify that ΔV does not decrease by more than 0.05 km/s. If ΔV decreases, the NLP is not even at a local minimum in the T_d direction.

**Result: PASS (all legs OK)**

```
Earth → 1943 Anteros      baseline 7.88    -0.5: +1.38   -0.1: +0.24   +0.1: +0.21   +0.5: +3.17
1943 Anteros → Bennu      baseline 9.30    -0.5: +0.78   -0.1: +0.04   +0.1: +0.02   +0.5: +0.58
101955 Bennu → 1989 ML    baseline 6.10    -0.5: +0.54   -0.1: +0.02   +0.1: +0.02   +0.5: +0.37
1989 ML → Earth           baseline 8.37    -0.5: +0.66   -0.1: +0.03   +0.1: +0.03   +0.5: +0.78
```

All perturbations increase ΔV, confirming the NLP solution is a local minimum in the T_d dimension. **However, this test does not probe T_t.** The local-minimum errors identified in 14.3 are in the T_t direction — the NLP is in the wrong basin at a different transfer time, not at a different departure time. This is why 14.5 passes while 14.3 shows large gaps on two legs.

---

## Summary

| Check | Result | Action |
|---|---|---|
| 14.1 Kepler residuals | Pass | None |
| 14.2 MILP gap | 3% — Warning | Fix NLP init; gap should close |
| 14.3 Pork chop NLP vs grid min | **2 legs off by 2–4 km/s** | Widen T_t scan in `initialize_mass_ratios` |
| 14.4 Brute-force enumeration | Skipped (4-body route) | Re-run after fixing init |
| 14.5 Perturbation sensitivity | Pass (T_d only) | Consider adding T_t perturbation |

The optimizer is not fabricating results, but it is finding a suboptimal solution. The route structure (which asteroids to visit) may still be correct, but the trajectory timing on at least two legs is trapped in local minima that cost an estimated **~6 km/s of unnecessary ΔV in total**.
