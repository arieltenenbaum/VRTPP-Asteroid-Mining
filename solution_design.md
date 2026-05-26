# Solution Design: Initialization Strategy Evaluation in VRTPP-PR

## Overview

This study evaluates a physics-informed, multi-start initialization strategy for Lambert-based trajectory optimization within the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) framework.

The paper's initialization (Section IV.A) uses T_d = 0 and the Hohmann transfer time as the NLP initial guess. The paper itself acknowledges this limitation: *"Although the Δv of its trajectory may be higher than the global optimum, it can be considered a trade-off solution… If minimizing Δv is the only consideration, the mission designer may use a different nonlinear optimization algorithm to find a global optimum, such as a grid search or meta-heuristic algorithm."* The proposed TA-grid is exactly that — a physics-informed grid search over departure phase rather than a uniform or arbitrary one.

The core physics insight is that departure Δv is sensitive to *where in the orbit* a spacecraft departs — its orbital phase angle — not just the calendar date. For eccentric orbits, low-cost departure windows cluster near periapsis and are non-uniformly distributed in time. When the paper seeds T_d = 0, it anchors at whatever orbital phase corresponds to the mission epoch, which for a high-eccentricity body may be far from periapsis. The proposed initialization addresses this on two axes: (1) **T_d** is sampled at 16 uniform true-anomaly positions (0°–337.5°) of the departure body, ensuring periapsis coverage regardless of epoch; (2) for each T_d candidate, **four T_t seeds** are evaluated — 0.5×T_t_hoh (fast), T_t_hoh (circular Hohmann), T_t_ecc (distance-corrected using the actual heliocentric departure distance), and 2×T_t_hoh (slow) — covering the range of physically plausible transfer durations. The best of up to 64 evaluations seeds an L-BFGS-B refinement.

Three experiments, corresponding to three research questions, evaluate the impact at arc, mechanism, and system levels.

---

## Research Questions

1. **Does orbital eccentricity predict when the paper's T_d=0 Hohmann initialization is trapped in a suboptimal local minimum for VRTPP-PR transfer arcs — and does TA-grid initialization systematically find lower-Δv solutions specifically for high-eccentricity NEA targets?**

2. **Do the arc cost improvements introduced by TA-grid initialization change the MILP's routing decisions in VRTPP-PR — and do the additional mining asteroids in the proposed model's routes correspond to arcs that were most improved in the initial mass ratio matrix?**

3. **Across varying fleet and asteroid catalog sizes in VRTPP-PR, does TA-grid initialization improve both mission value (mining visits, objective) and solver robustness (reducing trivial solutions and non-converged runs) relative to the paper's Hohmann initialization — and does the computational overhead remain proportionate?**

---

## Experiment 1: Eccentricity-Conditional Arc Cost Advantage

### Objective
Quantify how orbital eccentricity predicts the Δv gap between the paper's T_d=0 Hohmann initialization and TA-grid initialization across all VRTPP-PR transfer arcs — testing the hypothesis that the paper's seed is trapped in a suboptimal local minimum specifically for high-eccentricity targets.

### Method
- Compute arc costs (initial mass ratios) using:
  - Baseline model (`VRTPP-PaperModel.ipynb`, `main` branch — single Hohmann seed at T_d=0)
  - Proposed model (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — 16 TA-grid T_d candidates × 4 T_t seeds, L-BFGS-B refinement from best of up to 64 evaluations)
- Use identical asteroid sets and mission parameters

### Metrics

| Metric | Description |
|--------|-------------|
| Δv improvement per eccentricity band | Mean gap (baseline − proposed) for e < 0.2 vs e ≥ 0.2 |
| Per-body Δv gap (Earth → body arcs) | Individual gap sorted by target eccentricity — primary table |
| Max \|Δv diff\| | Worst-case discrepancy (single most improved arc) |
| Rank changes | Changes in ordering of lowest-cost arcs seen by MILP |

The 50/50 overall improvement split (half of arcs improved, half worse) is the expected null result: for low-eccentricity bodies the Δv landscape is nearly flat around the orbit, so T_d=0 and any TA-grid seed land in equivalent basins. The eccentricity-stratified breakdown is the primary metric; aggregate statistics alone are misleading.

### Output
- Eccentricity gap plot: Δv improvement vs. target eccentricity, with trend annotation (`exp1_eccentricity_gap.png`) — primary result
- Eccentricity-stratified summary: mean Δv improvement for e < 0.2 vs e ≥ 0.2 bodies (`exp1_dv_heatmap.png`)

### Purpose
Tests whether eccentricity is a reliable predictor of when the paper's initialization fails. For high-e bodies, T_d=0 seeds the NLP at an orbital phase that is likely far from periapsis, where the gradient-based solver converges to a worse local minimum. For near-circular bodies the phase makes little difference, so no improvement is expected — and none is observed. This confirms the TA-grid's advantage is geometrically motivated, not incidental.

---

## Experiment 2: Arc Cost Improvement → MILP Routing Consequence

### Objective
Demonstrate that the arc cost differences introduced by TA-grid initialization cause the MILP to select routes visiting additional mining asteroids — establishing the mechanistic link between the arc-level improvement in Experiment 1 and the system-level gains in Experiment 3.

### Method
1. Use the initial mass ratio matrices computed in Experiment 1 (one per model, no NLP iterations)
2. Run `build_milp` + `optimize` **once** with each matrix using identical problem parameters
3. Record which mining and refueling asteroids each model selects in its first-iteration route
4. For each asteroid added by the TA-grid route (not in paper route): record its eccentricity and Δv improvement from Experiment 1
5. For each asteroid in the paper route not selected by TA-grid: record same

This is a controlled isolation: holding the problem fixed and varying only the cost matrix reveals how much initialization quality alone drives routing differences, before any NLP refinement.

### Metrics

| Metric | Description |
|--------|-------------|
| First-iteration routes (both models) | Full visiting sequence before NLP updates |
| Bodies added by TA-grid route | Which asteroids appear only in the TA-grid MILP solution |
| Δv improvement for added bodies | Arc cost change from Exp 1 for those specific arcs |
| Bodies dropped from paper route | Which asteroids the TA-grid MILP de-selects |
| First-iteration MILP objective | Mission value at initialization only (no NLP refinement) |

### Output
- Route comparison table annotated with eccentricity and Δv improvement (`exp2_arc_cost_table.png`)
- Side-by-side route visualization showing added/dropped bodies (`exp2_routing_comparison.png`)

### Purpose
Demonstrates the causal chain: TA-grid finds lower arc costs for certain targets (Experiment 1) → those arcs appear cheaper in the MILP cost matrix → the MILP routes through those targets → more mining visits result (Experiment 3). This closes the mechanistic explanation for why initialization quality at the arc level produces mission-level improvement.

---

## Experiment 3: Full VRTPP-PR System Evaluation

### Objective
Quantify the extent to which TA-grid initialization improves mission value and solver robustness across varying fleet and asteroid catalog sizes — benchmarked against the paper's Table 6 configurations.

### Method
- Run both models:
  - Baseline (`VRTPP-PaperModel.ipynb`, `main` branch — paper's Hohmann-only init)
  - Proposed (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — 16 TA-grid T_d candidates × 4 T_t seeds, L-BFGS-B refinement)
- Use identical random asteroid sets (seeds 42–46 for our model; 42–44 for paper)
- Evaluate across: n_r ∈ {1, 2, 3}, n_m ∈ {4, 6, 8, 10}

### Metrics

**Mission Value**

| Metric | Description |
|--------|-------------|
| Mining asteroids visited (mean) | Primary mission value metric |
| Objective value | Combined profit − fuel penalty |
| Total Δv / propellant | Cost efficiency |

**Robustness**

| Metric | Description |
|--------|-------------|
| Trivial solution rate | Fraction of instances where no mining asteroid is visited |
| Non-converged run rate | Fraction of instances that do not converge within the iteration limit |
| Final MIP gap | MILP solution quality at termination |

**Scalability**

| Metric | Description |
|--------|-------------|
| Runtime (sec) | Computational cost per instance |
| Iterations to convergence | Convergence stability across problem sizes |

**Limitation:** At n_r=2, n_m=8, the proposed model's maximum MIP gap reaches 0.667, indicating the Gurobi time limit (30s) is binding at this scale. Mission value results at this configuration are lower bounds on what a longer time limit would achieve.

### Output
- Comparative results table (`experiments/results.csv`, `verification-suite` branch)
- Mining asteroids visited vs. model and problem size, convergence behavior (`exp3_convergence.png`)

### Purpose
Evaluates whether the arc-level and routing advantages demonstrated in Experiments 1–2 translate to consistent mission value and robustness improvements across the full range of problem scales from the paper's Table 6. The paper's own Table 6 reports 1–3 trivial solutions and 0–3 non-converged problems per configuration; reducing these failure modes is a direct, measurable improvement on the published baseline.

---

## Summary

The proposed evaluation framework isolates the impact of initialization at three levels:

1. **Arc level (Exp 1)** → Does orbital eccentricity predict when the paper's T_d=0 seed is trapped in a suboptimal local minimum, and does TA-grid initialization correct this for high-eccentricity NEAs?
2. **Mechanism level (Exp 2)** → Do those arc cost improvements cause the MILP to select routes visiting the affected asteroids — closing the causal chain from initialization to routing?
3. **System level (Exp 3)** → Do the routing improvements yield more mining visits and fewer solver failures across the full scalability configuration space?

Each experiment answers a distinct question; together they demonstrate that TA-grid initialization is a physics-motivated response to a limitation the paper itself identifies, with measurable and mechanistically explainable consequences at every level of the VRTPP-PR framework.
