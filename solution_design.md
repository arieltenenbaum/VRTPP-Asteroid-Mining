# Solution Design: Initialization Strategy Evaluation in VRTPP-PR

## Overview

This study evaluates a physics-informed, multi-start initialization strategy for Lambert-based trajectory optimization within the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) framework.

The paper's initialization (Section IV.A) uses T_d = 0 and the Hohmann transfer time as the NLP initial guess. The paper itself acknowledges this limitation: *"Although the Δv of its trajectory may be higher than the global optimum, it can be considered a trade-off solution… If minimizing Δv is the only consideration, the mission designer may use a different nonlinear optimization algorithm to find a global optimum, such as a grid search or meta-heuristic algorithm."* The proposed TA-grid is exactly that — a physics-informed grid search over departure phase rather than a uniform or arbitrary one.

The core physics insight is that departure Δv is sensitive to *where in the orbit* a spacecraft departs — its orbital phase angle — not just the calendar date. For eccentric orbits, low-cost departure windows cluster near periapsis and are non-uniformly distributed in time. When the paper seeds T_d = 0, it anchors at whatever orbital phase corresponds to the mission epoch, which for a high-eccentricity body may be far from periapsis. The proposed initialization addresses this on two axes: (1) **T_d** is sampled at 16 uniform true-anomaly positions (0°–337.5°) of the departure body, ensuring periapsis coverage regardless of epoch; (2) for each T_d candidate, **four T_t seeds** are evaluated — 0.5×T_t_hoh (fast), T_t_hoh (circular Hohmann), T_t_ecc (distance-corrected using the actual heliocentric departure distance), and 2×T_t_hoh (slow) — covering the range of physically plausible transfer durations. The best of up to 64 evaluations seeds an L-BFGS-B refinement.

Three experiments, corresponding to three research questions, evaluate the impact at arc, routing propagation, and system levels.

---

## Research Questions

1. **How does orbital geometry influence the sensitivity of Lambert-transfer cost estimation to initialization strategy in VRTPP-PR?**

2. **How do initialization-induced variations in transfer-cost estimation affect routing decisions in coupled asteroid mining logistics optimization?**

3. **What impact does initialization strategy have on mission performance, convergence behavior, and computational robustness across varying VRTPP-PR problem scales?**

---

## Experiment 1: Arc-Level — Orbital Geometry and Transfer Cost Sensitivity

### Objective
Quantify how orbital geometry predicts the Δv gap between the paper's T_d=0 Hohmann initialization and TA-grid initialization across VRTPP-PR transfer arcs — and demonstrate geometrically, via the Δv porkchop landscape, why the gap occurs for high-eccentricity targets.

### Method
- Compute arc costs (initial mass ratios) using:
  - Baseline model (`VRTPP-PaperModel.ipynb`, `main` branch — single Hohmann seed at T_d=0)
  - Proposed model (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — 16 TA-grid T_d candidates × 4 T_t seeds, L-BFGS-B refinement from best of up to 64 evaluations)
- Use identical asteroid sets and mission parameters
- For the porkchop overlay: generate standalone Δv landscapes for two representative body pairs — one high-eccentricity (Earth → 2001 SG10, e=0.425) and one low-eccentricity (Earth → Bennu, e=0.020) — and overlay the seed positions of both methods

### Metrics

| Metric | Description |
|--------|-------------|
| Δv improvement per eccentricity band | Mean gap (baseline − proposed) for e < 0.2 vs e ≥ 0.2 |
| Per-body Δv gap (Earth → body arcs) | Individual gap sorted by target eccentricity — primary table |
| Max \|Δv diff\| | Worst-case discrepancy (single most improved arc) |
| Rank changes | Changes in ordering of lowest-cost arcs seen by MILP |
| Porkchop basin comparison | Whether paper seed (T_d=0) lands in a local minimum for high-e vs low-e body |

The 50/50 overall improvement split (half of arcs improved, half worse) is the expected null result for low-eccentricity bodies — for near-circular orbits the Δv landscape is nearly flat, so any seed finds a comparable minimum. The eccentricity-stratified breakdown is the primary metric; an undifferentiated aggregate is misleading.

### Output
- `exp1_eccentricity_gap.png` — Δv improvement vs. target eccentricity (primary result)
- `exp1_dv_heatmap.png` — eccentricity-stratified summary: mean improvement for e < 0.2 vs e ≥ 0.2
- `exp1_porkchop_overlay.png` — porkchop Δv landscape for Earth → SG10 and Earth → Bennu with both methods' seed positions overlaid

### Purpose
Demonstrates that orbital geometry — primarily eccentricity — is the determinant of whether the paper's T_d=0 seed lands in a suboptimal local minimum. The porkchop overlay makes this visually concrete: for SG10 (e=0.425) the T_d=0 seed is stranded in a high-Δv basin far from periapsis, while TA-grid candidates cover the low-Δv periapsis window. For Bennu (e=0.020) the landscape is nearly flat and both methods find comparable minima — confirming the null result for low-eccentricity targets is mechanistically expected, not incidental.

---

## Experiment 2: Routing Propagation — Cost-Matrix Changes and MILP Routing Decisions

### Objective
Determine how initialization-induced variations in the transfer-cost matrix alter the MILP's routing decisions in VRTPP-PR — specifically, whether the additional mining asteroids selected by the proposed model correspond to arcs whose costs were most improved by TA-grid initialization.

### Method
1. Use the initial mass ratio matrices from Experiment 1 (one per model, no NLP iterations)
2. Run `build_milp` + `optimize` **once** with each matrix using identical problem parameters
3. Record which mining and refueling asteroids each model selects in its first-iteration route
4. For each asteroid added by the TA-grid route (not in paper route): record its Δv improvement from Experiment 1
5. For each asteroid in the paper route not selected by TA-grid: record same

This is a controlled isolation: holding the problem fixed and varying only the cost matrix reveals how much initialization quality alone drives routing differences, before any NLP refinement.

### Metrics

| Metric | Description |
|--------|-------------|
| First-iteration routes (both models) | Full visiting sequence before NLP updates |
| Bodies added by TA-grid route | Which asteroids appear only in the TA-grid MILP solution |
| Δv improvement for added bodies | Arc cost change from Exp 1 for those specific arcs |
| Bodies dropped from paper route | Which asteroids the TA-grid MILP de-selects |
| First-iteration MILP objective | Mission value from cost matrix alone, before any NLP refinement |

### Output
- `exp2_arc_cost_table.png` — which arcs changed between matrices, and whether those arcs appear in the selected routes
- `exp2_routing_comparison.png` — side-by-side route visualization annotated with Δv improvement per added/dropped body

### Purpose
Closes the mechanistic link between Experiment 1 and Experiment 3: TA-grid changes the cost matrix → the MILP sees certain arcs as cheaper → it routes through those asteroids → more mining visits result. This demonstrates that the system-level improvement is not incidental but is propagated directly from the arc-level advantage through the cost-matrix structure of the MILP.

---

## Experiment 3: System Level — Mission Performance, Convergence, and Computational Robustness

### Objective
Quantify the impact of initialization strategy on mission performance, convergence behavior, and computational robustness across varying fleet and asteroid catalog sizes in VRTPP-PR, benchmarked against the head-to-head "paper" vs "our_model" comparison in `experiments/results.csv`.

### Method
- Run both models:
  - Baseline (`VRTPP-PaperModel.ipynb`, `main` branch — paper's Hohmann-only init)
  - Proposed (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — 16 TA-grid T_d candidates × 4 T_t seeds, L-BFGS-B refinement)
- Use identical random asteroid sets (seeds 42–46 for our model; 42–44 for paper)
- Evaluate across: n_r ∈ {1, 2, 3}, n_m ∈ {4, 6, 8, 10}

### Metrics

**Mission Performance**

| Metric | Description |
|--------|-------------|
| Mining asteroids visited (mean) | Primary mission value metric |
| Objective value | Combined profit − fuel penalty |
| Total Δv / propellant | Cost efficiency |

**Convergence Behavior**

| Metric | Description |
|--------|-------------|
| Iterations to convergence (min/max/mean) | How quickly and stably the algorithm converges |
| Non-converged run rate | Fraction of instances that do not converge within the iteration limit |

**Computational Robustness**

| Metric | Description |
|--------|-------------|
| Trivial solution rate | Fraction of instances where no mining asteroid is visited |
| Final MIP gap (min/max/mean) | MILP solution quality at termination |
| Runtime (sec) | Computational cost per instance |

**Limitation:** At n_r=2, n_m=8, the proposed model's maximum MIP gap reaches 0.667, indicating the Gurobi time limit (30s) is binding at this scale. Mission value results at this configuration are lower bounds on what a longer time limit would achieve.

### Output
- Comparative results table (`experiments/results.csv`, `verification-suite` branch)
- Mining asteroids visited and convergence behavior vs. model and problem size (`exp3_convergence.png`)

### Purpose
Evaluates whether the arc-level and routing advantages demonstrated in Experiments 1–2 translate to consistent improvements in mission value, convergence stability, and robustness across the full scalability configuration space. Convergence behavior and robustness are distinct dimensions: better initialization leads both to more productive iteration trajectories (genuine convergence over more iterations vs. early false convergence) and to fewer outright failures (trivial solutions and non-convergent runs).

---

## Summary

The proposed evaluation framework isolates the impact of initialization at three levels:

1. **Arc level (Exp 1)** → How does orbital geometry determine whether the paper's T_d=0 Hohmann seed finds a suboptimal local minimum — and does the porkchop landscape explain why high-eccentricity NEAs are most affected?
2. **Routing propagation level (Exp 2)** → How do the initialization-induced cost matrix differences propagate through the MILP to alter routing decisions — and do the added bodies correspond to arcs most improved by TA-grid?
3. **System level (Exp 3)** → What is the aggregate impact on mission performance, convergence behavior, and computational robustness across varying problem scales?

Each experiment answers a distinct question; together they demonstrate that TA-grid initialization is a physics-motivated response to a limitation the paper itself identifies, with measurable and mechanistically explainable consequences at every level of the VRTPP-PR framework.
