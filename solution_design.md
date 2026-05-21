# Solution Design: Initialization Strategy Evaluation in VRTPP-PR

## Overview

This study evaluates a physics-informed, multi-start initialization strategy for Lambert-based trajectory optimization within the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) framework.

The core physics insight is that departure Δv is sensitive to *where in the orbit* a spacecraft departs — its orbital phase angle — not just the calendar date. For eccentric orbits, low-cost departure windows cluster near periapsis and are non-uniformly distributed in time. The proposed TA-grid addresses this by sampling 16 uniform true-anomaly positions across the feasible departure window, ensuring coverage of phase-dependent Δv structure that a time-uniform Hohmann seed misses.

The goal is to quantify how much initialization choice affects **arc-cost accuracy, routing decisions, and mission-level outcomes** in asteroid mining logistics — specifically, the extent of its impact within the VRTPP-PR coupled MILP-NLP framework — and to demonstrate that the TA-grid's coverage is geometrically interpretable in terms of orbital mechanics.

Three experiments, corresponding to three research questions, evaluate the impact at arc, interpretability, and system levels.

---

## Research Questions

1. **By how much does TA-grid initialization reduce arc Δv estimation error in VRTPP-PR, and does the magnitude of improvement vary systematically with target orbit eccentricity across the asteroid catalog?**

2. **To what extent do the TA-grid's departure windows correspond to physically meaningful orbital phases — and can this geometric coverage explain the eccentricity-dependent performance gap observed in the arc-cost matrix?**

3. **Across varying fleet sizes and asteroid catalog sizes, to what extent does TA-grid initialization improve mining visit count and scalability in the VRTPP-PR system relative to the paper model?**

---

## Experiment 1: Arc-Cost Matrix Comparison

### Objective
Quantify how much initialization changes the **Δv / mass-ratio matrix** used by the MILP, and determine whether the magnitude of improvement correlates with target orbit eccentricity.

### Method
- Compute arc costs using:
  - Baseline model (`VRTPP-PaperModel.ipynb`, `main` branch — single Hohmann seed at T_d=0)
  - Proposed model (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — TA-grid + distance-corrected T_t seeds)
- Use identical asteroid sets and mission parameters

### Metrics

| Metric | Description |
|------|------------|
| Mean Δv difference | Average change in arc cost across all arcs |
| Max Δv difference | Worst-case discrepancy |
| % arcs improved | Fraction where proposed method finds lower Δv |
| Rank changes | Changes in ordering of lowest-cost arcs |
| Route-relevant arc changes | Differences in arcs likely selected by MILP |
| Δv improvement by eccentricity | Per-body Δv gap (baseline − proposed) sorted by target eccentricity |

### Output
- Heatmap of Δv differences between models (`exp1_dv_heatmap.png`)
- Summary statistics table (`exp1_summary_table.png`)
- Eccentricity gap plot: Δv improvement vs. target eccentricity (`exp1_eccentricity_gap.png`)

### Purpose
Determines whether initialization changes the **cost landscape seen by the routing solver**, and whether the improvement is predicted by the eccentric orbit structure of the asteroid catalog.

---

## Experiment 2: Departure Window Coverage and Interpretability

### Objective
Determine whether the TA-grid's initialization seeds correspond to physically meaningful orbital phases, and whether geometric coverage of the Δv landscape explains which local optima each method finds.

### Method
1. Select the paper's canonical route: Earth → 1996 FG3 → 101955 Bennu → Earth
2. Cold-start NLP for each leg (no warm-start) using each model's own init logic
3. Record the (T_d, T_t) found by each method per leg
4. Overlay each method's seed points on the Δv porkchop landscape for representative high- and low-eccentricity arcs

### Metrics

| Metric | Description |
|------|------------|
| Departure time per leg | Which calendar window each method selects |
| Transfer time per leg | Which trajectory arc each method finds |
| Δv per leg | Cost at the found local optimum |
| Seed coverage fraction | % of TA-grid seeds within 20% of the porkchop global minimum |
| Baseline seed coverage | Same metric for Hohmann seeds |

### Output
- Per-leg trajectory parameters table (`exp2_leg_table.png`)
- Mission timeline comparison (`exp2_timeline.png`)
- Porkchop overlay: seed positions for both methods annotated on Δv landscape for one low-e arc (e.g., Earth → Bennu, e=0.020) and one high-e arc (e.g., Earth → 2001 SG10, e=0.425)

### Purpose
Demonstrates that the TA-grid's advantage is **geometrically interpretable**: its seeds systematically cover the periapsis-adjacent low-Δv region for eccentric bodies, whereas the Hohmann seeds land at an arbitrary phase that may be far from the global minimum. This directly explains the eccentricity-dependent gap from Experiment 1.

---

## Experiment 3: Full VRTPP-PR System Evaluation

### Objective
Quantify the **extent** to which TA-grid initialization improves mining visit count and computational scalability across varying fleet and asteroid catalog sizes in VRTPP-PR.

### Method
- Run both models:
  - Baseline (`VRTPP-PaperModel.ipynb`, `main` branch — paper's Hohmann-only init)
  - Proposed (`VRTPP_PR_Optimization.ipynb`, `periapsis-init` branch — TA-grid init)
- Use identical random asteroid sets (seeds 42–46 for our_model; 42–44 for paper)
- Evaluate across problem sizes: n_r ∈ {1, 2, 3}, n_m ∈ {4, 6, 8, 10}

### Metrics

| Metric | Description |
|------|------------|
| Mining asteroids visited | Mission value |
| Total Δv / propellant | Cost efficiency |
| Objective value | Overall performance |
| Iterations to convergence | Stability |
| Runtime (sec) | Computational cost |
| Trivial solutions | Failure cases |
| Non-converged problems | Robustness |
| Final MIP gap | MILP solution quality |

### Output
- Comparative results table (`experiments/results.csv`, `verification-suite` branch)
- Plots of mining asteroids vs. model, runtime vs. problem size, convergence behavior (`exp3_convergence.png`)

### Purpose
Evaluates the magnitude of improvement in **end-to-end mission value** across problem scales — specifically, how many more mining asteroids the TA-grid enables the VRTPP-PR system to visit per mission.

---

## Summary

The proposed evaluation framework isolates the impact of initialization at three levels:

1. **Arc level** → by how much does the TA-grid reduce Δv estimation error, and does eccentricity predict the magnitude? (Exp 1)
2. **Interpretability level** → do the TA-grid's departure windows correspond to physically meaningful orbital phases, and can this explain the eccentricity gap? (Exp 2)
3. **System level** → to what extent does initialization improve mission value and scalability in the full VRTPP-PR system? (Exp 3)

This multi-level approach ensures that improvements are assessed in the **context of asteroid mining logistics**, with each experiment quantifying the *extent* of impact rather than merely whether an impact exists.
