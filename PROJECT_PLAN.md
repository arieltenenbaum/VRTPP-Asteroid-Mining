# VRTPP-PR Asteroid Mining — Project Plan

**Paper:** Choi & Ho, "Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization," AIAA SciTech 2026.

---

## What This Project Is

An iterative **MILP–NLP optimizer** for asteroid mining mission planning. The algorithm alternates between:

1. **MILP** (Gurobi) — given fixed Δv cost estimates for all possible arcs, find the optimal visiting sequence and refueling strategy for multiple spacecraft.
2. **NLP** (scipy + Lambert solver) — given fixed routes, optimize departure time (T_d) and transfer time (T_t) per arc to minimize Δv; update mass ratios.

Repeat until convergence (Δv change < tolerance across consecutive identical routes).

---

## Problem Setup

| Parameter | Value |
|-----------|-------|
| Base | Earth (3 virtual copies for multi-spacecraft) |
| Refueling asteroids | 162173 Ryugu, 101955 Bennu |
| Mining asteroids | 2001 SG10, 1989 ML, 1996 FG3, 2001 CC21, 1943 Anteros |
| Spacecraft count | Up to 3; dry mass = 300 kg, max wet mass = 20,000 kg |
| Propellant (Isp) | 457 s |
| Objective | Maximize `profit − λ × fuel`, λ = 5×10⁻⁵ kg⁻¹ |
| Profit per mining visit | 10 (10 kg mass collected) |
| Epoch | JD 2461000.5 ≈ April 2025 |
| Time unit | 1 TU = 58.132 days |
| Orbital elements | Table 3 of paper |

---

## Paper's Target Result

| Segment | Δv [km/s] | Departure Time [TU] | Transfer Time [TU] |
|---------|-----------|--------------------|--------------------|
| Earth → 1996 FG3 | 9.51 | 0.09 | 6.26 |
| FG3 → 101955 Bennu | 7.32 | 8.83 | 7.06 |
| Bennu → Earth | 8.17 | 17.59 | 6.81 |

**Paper setup**: n_bv = 3 spacecraft (Table 2); the optimizer returns a 1-spacecraft solution for this case study. 10 iterations, ~10.7 s (Windows/Intel Core Ultra 9). Objective ≈ 9.28.

---

## Current Results by Branch

### `main` branch — `VRTPP_PR_Optimization.ipynb` (2D fixed grid init)

```
Spacecraft 1: Earth → 1943 Anteros → 101955 Bennu → 1989 ML → Earth
```

Objective ≈ **18.93** (3 mining visits = 30 profit − fuel penalty). Converges in ~23 iterations (soft convergence).

### `bang-ahn-grid-init` branch — `VRTPP_PR_Optimization.ipynb` (adaptive grid init)

```
Spacecraft 1: Earth → 2001 CC21 → Earth
Spacecraft 2: Earth → 162173 Ryugu → 1943 Anteros → Earth
Spacecraft 3: Earth → 162173 Ryugu → 1989 ML → Earth
```

Objective ≈ **28.20** (3 mining visits = 30 profit − fuel penalty). Converges in ~22 iterations, ~15 min (macOS/M2 Max).

Both results outperform the paper's objective of ≈ 9.28 (1 mining visit). The different routes arise from different initialization strategies leading to different locally stable MILP–NLP solutions. Neither algorithm guarantees the global optimum.

---

## Repository Branch Map

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Core MILP–NLP optimizer with NLP warm-start + 2D grid initialization | Working; produces obj ≈ 28.2 |
| `verification-suite` | Scalability experiments (n_r × n_m grid) vs. paper Table 6; includes Section 14 optimizer health checks | Verification suite set up for `main`'s notebook only — **NOT yet configured for `bang-ahn-grid-init`** |
| `bang-ahn-grid-init` | Experimental: adaptive grid sizing derived from orbital mean motions (Bang & Ahn approach) | Working; produces same route as main; under validation |

---

## Two Notebooks Explained

Both notebooks share the same MILP formulation, orbital mechanics, index sets, and parameters. They differ in initialization strategy and scope.

### `VRTPP_PR_Optimization.ipynb` — Primary Implementation

- Used in: `main`, `verification-suite`, `bang-ahn-grid-init`
- **Initialization**: 2D grid scan (T_d × T_t) then L-BFGS-B refinement; warm-starts NLP from previous iteration's (T_d, T_t)
- **NLP bounds**: T_d_max = T_d_min + 5 TU; T_t_max = 30 TU
- Has 13 bugs fixed across 8 sessions
- Contains porkchop plots (paper Fig. 2) and Section 14 verification suite

### `VRTPP-PaperModel.ipynb` — Paper-Faithful Reference

- Used in: `main` only
- **Initialization**: 1D T_t scan at T_d = 0 (close to paper's Hohmann-only description) then `trust-constr` NLP
- **NLP bounds**: No upper bound on T_d (follows paper Eq. 44 literally)
- Written clean without bug history; serves as controlled reference
- Contains: Δv landscape diagnostics (Cell 18), Experiment 3 paper route verification (Cells 30–31), route visualization

**Why two notebooks exist:** `VRTPP-PaperModel.ipynb` was created to answer "if we follow the paper's algorithm literally, can we reproduce their Earth→FG3→Bennu→Earth route?" It isolates solver behavior from implementation choices.

---

## The Bang & Ahn Branch (`bang-ahn-grid-init`)

Addresses the known local-minimum problem in initialization. Four changes to `VRTPP_PR_Optimization.ipynb`:

| Change | Cell | What |
|--------|------|------|
| Adaptive grid step sizes in `initialize_mass_ratios` | 21 | Steps derived from orbital mean motions: `T_d_step = clip(2π/n_fast/4, 0.75, 2.5)` TU |
| 2D adaptive scan in `optimize_segment` | 14 | Scans both T_d and T_t before L-BFGS-B (was: 1D T_t scan at fixed T_d) |
| `mean_motion` property on `OrbitalBody` | 4 | Computed property for the adaptive formula |
| Removed warm-start plumbing from `solve_vrtpp_pr` | 24 | 2D scan makes warm-starting unnecessary; warm-start was causing cascade failures |

**The cascade problem (key debugging finding):** The optimizer found Earth→FG3 at 6.60 km/s (T_d = 4.07 TU) instead of the paper's 9.51 km/s (T_d = 0.09 TU). This is a genuinely cheaper leg in isolation, but it shifts FG3's arrival time past the optimal FG3→Bennu departure window, forcing all downstream legs into worse geometry. **Fix:** Earth departure capped at T_d ≤ 2.0 TU in both Cell 14 and Cell 21.

For full details see `BANG_AHN_CHANGES.md`.

---

## Verification Suite (`verification-suite` branch)

Runs the optimizer over all combinations of n_r ∈ {1,2,3} refueling asteroids and n_m ∈ {4,6,8,10} mining asteroid candidates, recording iteration counts, wall-clock time, and mining visits to compare against paper Table 6.

**⚠ Important:** The verification suite is configured to run `VRTPP_PR_Optimization.ipynb` from the `main` branch. It has **not yet been set up to test the `bang-ahn-grid-init` notebook**. Running the scalability experiment on the bang-ahn branch is a planned next step — but only after that branch is fully validated.

### Section 14 Health Checks (inside `VRTPP_PR_Optimization.ipynb`)

| Check | Result | Action needed |
|-------|--------|---------------|
| 14.1 Kepler residuals | PASS | None |
| 14.2 MILP optimality gap | WARNING (3%) | Fix NLP init; gap should close |
| 14.3 Porkchop NLP vs grid minimum | **2 legs off by 2–4 km/s** | Widen T_t scan in `initialize_mass_ratios` |
| 14.4 Brute-force enumeration | Skipped (4-body route) | Re-run after fixing init |
| 14.5 Perturbation sensitivity | PASS (T_d direction only) | Consider adding T_t perturbation |

Root cause of 14.2 and 14.3: initialization grid scans T_t only up to 13 TU in steps of 2 TU — too coarse for some body pairs. The `bang-ahn-grid-init` branch is intended to fix this.

---

## Known Limitations

| Issue | Impact | Status |
|-------|--------|--------|
| Fixed initialization grid too coarse | NLP can land in wrong Δv basin; ~6 km/s excess Δv on some legs | Being fixed in `bang-ahn-grid-init` |
| T_d_max = T_d_min + 5 TU hardcoded | Paper case study specifies 2-day max service time; should be a named variable (`T_service_max = 2 / 58.132` TU) not a magic number | Needs fixing in both notebooks |
| Soft convergence fallback | May declare convergence with slight NLP oscillation | Acceptable; prevents infinite cycling when NLP oscillates between near-identical basins |
| No multi-objective optimization | Cannot explore profit/fuel trade-off surface | Future feature |
| Gurobi license | Must run locally on the licensed machine | Permanent constraint |

---

## Paper Gaps (Known Deviations from Paper Description)

1. **Platform sensitivity:** Paper's Hohmann-only init works on Windows/Intel; on macOS/M2 the same starting point lands in a different Δv basin. Fixed with T_t scan.
2. **"No solutions" / infeasible MILP:** Paper doesn't describe this failure mode. Caused by wrong-basin initialization producing mass ratios that make all routes infeasible. Fixed by correct initialization.
3. **Route oscillation:** Paper's convergence criterion assumes stable routes; doesn't address cycling. Fixed with soft fallback (5+ stable iterations + Δv change < 0.05).
4. **Virtual node propagation:** Paper doesn't describe how to handle mass ratios for virtual-node arc copies. `VRTPP-PaperModel.ipynb` propagates NLP results to all virtual copies of each physical arc.
5. **NLP T_d upper bound hardcoded as 5 TU:** The paper case study specifies a 2-day maximum service time at any asteroid. The notebook should define this as a named parameter (`T_service_max = 2 days = 2/58.132 TU ≈ 0.034 TU`) and derive the NLP upper bound from it, rather than using the arbitrary 5 TU magic number.

---

## Workflow Constraints

- **Gurobi runs locally only** — license tied to local machine
- Code must be run in Jupyter, outputs copied manually for analysis
- `main` branch is the stable reference; `bang-ahn-grid-init` is experimental

---

## Open Questions / Next Steps

1. **Main branch — faithful paper replication**  
   `VRTPP_PaperModel.ipynb` should replicate the paper's formulation, parameters, and Hohmann-based initialization exactly. The paper's setup uses n_bv = 3 (Table 2); a 1-spacecraft solution is what the paper's optimizer returns for the case study, not a forced constraint. Goal: reproduce Table 5 (Earth → 1996 FG3 → 101955 Bennu → Earth, obj ≈ 9.28, ~10 iterations).

2. **bang-ahn-grid-init — validate and justify the modified initialization**  
   Demonstrate that the Bang-Ahn adaptive grid is a conceptually sound and well-motivated replacement for the paper's Hohmann-based initialization. The goal is to produce a research justification — why the initialization was changed, what problem it solves, and what improvement it provides — suitable for inclusion in a research paper.

3. **Verification suite — run after bang-ahn is validated**  
   Once `bang-ahn-grid-init` is fully debugged, diagnosed, and experimentally characterized, run the n_r × n_m scalability experiments (paper Table 6) using the validated bang-ahn notebook. Do not run the verification suite on `main`'s `VRTPP_PR_Optimization.ipynb`.

---

## File Reference

| File | Branch | Description |
|------|--------|-------------|
| `VRTPP_PR_Optimization.ipynb` | all | Primary optimizer notebook |
| `VRTPP-PaperModel.ipynb` | main | Paper-faithful reference notebook |
| `BANG_AHN_CHANGES.md` | bang-ahn-grid-init | Full change log, cascade problem analysis, expected results |
| `Bang_Ahn_Change1_Explanation.md` | bang-ahn-grid-init | Deep-dive on adaptive grid sizing |
| `INITIALIZATION_EXPLAINED.md` | main | How grid scan, L-BFGS-B, and warm-start work |
| `MODEL_COMPARISON_AND_VALIDATION.md` | all | Paper vs. implementation comparison; notebook comparison (§9) |
| `VERIFICATION.md` | verification-suite | Section 14 health check findings and recommended fixes |
| `experiments/experiment_scalability.ipynb` | verification-suite | Scalability experiment runner |
| `experiments/results.csv` | verification-suite | Results table (paper Table 6 values filled; our model rows empty) |
| `experiments/README.md` | all | Column definitions and paper Table 6 reference values |
| `HANDOVER_2026-05-06.md` | bang-ahn-grid-init | Latest session notes (bugs fixed, known behavior, next steps) |
| `HANDOVER_2026-04-27.md` | main | Previous session notes (paper gaps, notebook comparison) |
