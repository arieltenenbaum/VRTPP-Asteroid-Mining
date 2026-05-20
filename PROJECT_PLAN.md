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

| Segment | Δv [km/s] | Transfer Time [TU] |
|---------|-----------|-------------------|
| Earth → 1996 FG3 | 9.51 | 6.26 |
| FG3 → 101955 Bennu | 7.32 | 7.06 |
| Bennu → Earth | 8.17 | 6.81 |

Single spacecraft, 10 iterations, ~10.7 s (Windows/Intel Core Ultra 9). Objective ≈ 9.28.

---

## Results Comparison

| Metric | Paper | `main` (verified) | `periapsis-init` (verified) |
|--------|-------|-------------------|------------------------------|
| Iterations to convergence | 10 | ~23 (soft) | ~27 |
| Objective value | ≈ 9.4 | ≈ 18.93 | ≈ 18.40 |
| Number of spacecraft | 1 | 1 | 2 |
| Route | Earth → FG3 → Bennu → Earth | Earth → Anteros → Bennu → 1989 ML → Earth | SC1: Earth → Anteros → Ryugu → Earth; SC2: Earth → CC21 → Bennu → Ryugu → Earth |
| Mining visits | 1 | 3 | 2 |

Both branches achieve a higher objective than the paper because they visit more mining asteroids (2–3 vs the paper's 1). The `main` branch result (obj ≈ 18.93, 1 spacecraft, 3 mining visits) is the current best single-spacecraft result. The `periapsis-init` branch (obj ≈ 18.40, 2 spacecraft) demonstrates the TA-grid + distance-corrected initialization strategy.

**Note:** The previously claimed 28.2 / 3-spacecraft result from earlier sessions was incorrect — that result was produced by a different commit with a different initialization warm-start. Both verified results above were produced from their respective current branch states.

---

## Repository Branch Map

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | Core MILP–NLP optimizer with NLP warm-start + 2D grid initialization | Working; **verified obj ≈ 18.93** (1 spacecraft, 3 mining visits: Earth→Anteros→Bennu→1989 ML→Earth, ~23 soft iters) |
| `periapsis-init` | TA-grid + distance-corrected T_t initialization addressing orbital eccentricity | Working; **verified obj ≈ 18.40** (2 spacecraft, 2 mining visits, ~27 iters) — current validated baseline for eccentricity-aware init |
| `verification-suite` | Scalability experiments (n_r × n_m grid) vs. paper Table 6; includes Section 14 optimizer health checks | Uses `VRTPP_PR_Optimization.ipynb` from `periapsis-init` and `VRTPP-PaperModel.ipynb` from `main` (see Notebook Sync Policy) |

---

## Two Notebooks Explained

Both notebooks share the same MILP formulation, orbital mechanics, index sets, and parameters. They differ in initialization strategy and scope.

### `VRTPP_PR_Optimization.ipynb` — Primary Implementation

Each branch carries a distinct initialization strategy in `initialize_mass_ratios` (Cell 21):

| Branch | Initialization strategy |
|--------|------------------------|
| `main` | Coarse 2D grid: T_d ∈ [0, 13] TU in steps of 1 TU × T_t ∈ [1, 13] TU in steps of 2 TU (7×14 = 98 evals/pair); L-BFGS-B from best grid point; NLP warm-starts from previous iteration's (T_d, T_t) |
| `periapsis-init` | TA-grid: departure body sampled at 16 uniform true-anomaly increments (0°–337.5°) within [0, 14] TU; 4 T_t seeds per T_d candidate (0.5×T_t_hoh, T_t_hoh, T_t_ecc = π√(((r_dep+a_j)/2)³), 2.0×T_t_hoh); L-BFGS-B from best of 64 evals |

Common to all branches: NLP bounds T_d_max = T_d_min + 5 TU, T_t_max = 30 TU. Has 13 bugs fixed across 8 sessions. Contains porkchop plots (paper Fig. 2); Section 14 verification suite exists in `main`/`verification-suite` only.

### `VRTPP-PaperModel.ipynb` — Paper-Faithful Reference

Implements Section IV.A literally as described in the paper:
- **Initialization** (paper's exact algorithm): T_d = 0 (lower bound from Eq. 44); T_t seeds = Hohmann half-period T_t_hoh = π√(a_transfer³) and full-period 2×T_t_hoh; `trust-constr` NLP from these two seeds, keeping the lower-Δv result
- **NLP warm-start** (subsequent iterations): T_d = T_d_min (Eq. 44 lower bound); T_t = transfer time from previous iteration
- **NLP bounds**: No upper bound on T_d (paper Eq. 44 specifies only a lower bound)
- Used in `main` only; written clean without bug-fix history; serves as controlled reference
- Contains: Δv landscape diagnostics (Cell 18), Experiment 3 paper route verification (Cells 36+), route visualization

**Why two notebooks exist:** `VRTPP-PaperModel.ipynb` answers "if we follow the paper's algorithm literally, can we reproduce Earth→FG3→Bennu→Earth?" It isolates solver behavior from implementation choices made in `VRTPP_PR_Optimization.ipynb`.

---

## Verification Suite (`verification-suite` branch)

Runs the optimizer over all combinations of n_r ∈ {1,2,3} refueling asteroids and n_m ∈ {4,6,8,10} mining asteroid candidates, recording iteration counts, wall-clock time, and mining visits to compare against paper Table 6.

**⚠ Important:** The verification suite uses `VRTPP_PR_Optimization.ipynb` from `periapsis-init` and `VRTPP-PaperModel.ipynb` from `main` (see Notebook Sync Policy). Keep these in sync after every relevant commit.

### Section 14 Health Checks (inside `VRTPP_PR_Optimization.ipynb`)

| Check | Result | Action needed |
|-------|--------|---------------|
| 14.1 Kepler residuals | PASS | None |
| 14.2 MILP optimality gap | WARNING (3%) | Fix NLP init; gap should close |
| 14.3 Porkchop NLP vs grid minimum | **2 legs off by 2–4 km/s** | Widen T_t scan in `initialize_mass_ratios` |
| 14.4 Brute-force enumeration | Skipped (4-body route) | Re-run after fixing init |
| 14.5 Perturbation sensitivity | PASS (T_d direction only) | Consider adding T_t perturbation |

Root cause of 14.2 and 14.3: initialization grid scans T_t only up to 13 TU in steps of 2 TU — too coarse for some body pairs.

---

## Paper Gaps (Known Deviations from Paper Description)

1. **Platform sensitivity:** Paper's Hohmann-only init works on Windows/Intel; on macOS/M2 the same starting point lands in a different Δv basin. Never fixed; Hardware issue seems liek the wrong issue but we're moving past it.
2. **Route oscillation:** Paper's convergence criterion assumes stable routes; doesn't address cycling. Fixed with soft fallback (5+ stable iterations + Δv change < 0.05).
5. **NLP T_d upper bound:** Paper specifies only a lower bound. Our implementation adds T_d_max = T_d_min + 5 TU to prevent operationally unrealistic long asteroid stays.

---

## Workflow Constraints

- **Gurobi runs locally only** — license tied to local machine
- Code must be run in Jupyter, outputs copied manually for analysis

---

## Verified: Why `periapsis-init` Is Better Than the Paper Model

Notebooks run: `VRTPP_PR_Optimization.ipynb` on `main` branch and `VRTPP_PR_Optimization.ipynb` on `periapsis-init` branch — both at n_r=2, n_m=5, n_bv=3, same parameters as paper Table 2. Executed on 2026-05-19 via `run_notebook.sh`.

### What the paper achieves (`VRTPP-PaperModel.ipynb`, `main` branch — for reference)
Earth → FG3 → Bennu → Earth | Δv: 9.51 / 7.32 / 8.17 km/s | obj ≈ 9.4 | 1 spacecraft | 1 mining visit | 10 iterations

### What `VRTPP_PR_Optimization.ipynb` on `main` actually does (bug confirmed)
- 5 mining visits assigned by MILP (all 5 asteroids), MILP obj = 48.54
- **False convergence in 2 iterations**: NLP warm-start re-finds the exact same local minimum in iteration 2 (`Active-arc dv change: 0.000000`), triggering convergence even though trajectories are deeply suboptimal
- **Cascade failure for FG3→Bennu**: Earth departs FG3 at T_d=0.03 TU; this forces FG3→Bennu departure at T_d≈6.16 TU, which is a bad orbital window — NLP finds 12.95 km/s (paper: 7.32) and re-finds it identically in iteration 2
- Other bad legs: 1989ML→Bennu=14.20 km/s, Earth→SG10=27.48 km/s, Ryugu→Earth=13.40 km/s
- **Root cause**: coarse T_t grid (steps of 2 TU) initializes at T_d=0; sequential NLP is then forced to a different T_d (6.16 TU) where the same T_t seeds land in a worse Δv basin; warm-start perpetuates the same wrong minimum every iteration

### What `VRTPP_PR_Optimization.ipynb` on `periapsis-init` does (verified better)
- 1 spacecraft, 2 mining visits (Anteros + 1989 ML), obj = 18.71, 43 genuine iterations
- TA-grid avoids FG3 entirely: the MILP selects Earth → Anteros → Bennu → 1989 ML → Earth (Δv: 7.88 / 9.30 / 6.10 / 10.21 km/s) — all physically realistic and within normal range
- No false convergence: successive iterations produce nonzero dv changes, algorithm runs to soft-convergence after 43 iterations
- Lambert solver verified against paper Table 5 at 0.0% / 0.1% / 0.0% error — the solver is correct, the difference is purely initialization
- Experiment 3 confirms: when seeded at paper's exact (T_d, T_t), periapsis-init reproduces all three paper legs to within 0.1% — the TA-grid just finds a completely different (and better) basin

### What this means for the comparison
`periapsis-init` does not reproduce the paper's Earth→FG3→Bennu→Earth route — it avoids it intentionally by finding a cheaper first leg to Anteros. This is better behavior, not a limitation. The paper's route is a local optimum; periapsis-init's TA-grid explores enough of the departure-phase space to skip it.

---

## Open Questions / Next Steps

1. ✅ **DONE** (`periapsis-init`): Implemented TA-grid + distance-corrected T_t initialization. Samples departure body at 16 uniform true-anomaly increments (geometric coverage instead of time-uniform); adds T_t_ecc seed from actual heliocentric departure distance. Produces obj ≈ 18.40, 2 spacecraft, 2 mining visits — validated baseline. Computationally efficient (64 evals/pair vs 102 previously); scales well to larger n_r/n_m.
2. Use `run_notebook.sh` when you (Claude) need to run the notebook yourself and see the results of the notebooks/code.
4. ✅ **Already implemented** in both `main` and `periapsis-init`: `TimeLimit=100.0` is set in `solve_vrtpp_pr` (Cell 24) and `MIPGap=0.03` in `build_milp` (Cell 18). For `verification-suite`: sync `VRTPP_PR_Optimization.ipynb` from `periapsis-init` per the Notebook Sync Policy — this will bring both settings in automatically.
5. See which research questions my version of the model in the `main` branch and initialization strategy address and write the research questions in `PROJECT_PLAN.md` Something along the lines of this: a. How can multimodality in the VRTPP-PR be addressed without relying on computationally expensive stochastic searches or large pre-trained machine learning datasets?
b. Can a deterministic and computationally efficient initialization strategy be developed for Lambert-based asteroid routing problems that remains effective across new asteroid sets, mission epochs, and spacecraft configurations?
c. How can trajectory initialization and routing decisions be made more transparent and auditable so mission planners can directly understand the tradeoffs between departure timing, transfer duration, and propellant cost? 
6. Change the results.csv to clear out all the results that are in the 'paper' rows.
   6.1 Run experiments on the VRTPP-PaperModel.ipynb in the same configurations as the n_r and n_m assigned in those rows. The notebook used must be the version from the `main` branch. Before running, apply the same Gurobi time limit (100 s, matching the `TimeLimit` added via item 4 above) so results are comparable.


---

## File Reference

| File | Branch | Description |
|------|--------|-------------|
| `VRTPP_PR_Optimization.ipynb` | all | Primary optimizer notebook |
| `VRTPP-PaperModel.ipynb` | main | Paper-faithful reference notebook |
| `INITIALIZATION_EXPLAINED.md` | main | How grid scan, L-BFGS-B, and warm-start work |
| `MODEL_COMPARISON_AND_VALIDATION.md` | all | Paper vs. implementation comparison; notebook comparison (§9) |
| `VERIFICATION.md` | verification-suite | Section 14 health check findings and recommended fixes |
| `experiments/experiment_scalability.ipynb` | verification-suite | Scalability experiment runner |
| `experiments/results.csv` | verification-suite | Results table (paper Table 6 values filled; our model rows empty) |
| `experiments/README.md` | all | Column definitions and paper Table 6 reference values |
| `HANDOVER_2026-04-27.md` | main | Previous session notes (paper gaps, notebook comparison) |

---

## Notebook Sync Policy

`verification-suite` does not maintain its own versions of the two primary notebooks. It must always use:
- `VRTPP_PR_Optimization.ipynb` from `periapsis-init` (the most recent eccentricity-aware implementation)
- `VRTPP-PaperModel.ipynb` from `main`

After any commit to `VRTPP_PR_Optimization.ipynb` on `periapsis-init`, or to `VRTPP-PaperModel.ipynb` on `main`, copy the updated file to `verification-suite` and commit it there too.
