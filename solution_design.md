# Solution Design: Initialization Strategy Evaluation in VRTPP-PR

## Overview

This study evaluates a physics-informed, multi-start initialization strategy for Lambert-based trajectory optimization within the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) framework.

The goal is not to improve trajectory optimization in isolation, but to understand how initialization affects **routing decisions, convergence behavior, and mission-level outcomes** in asteroid mining logistics.

To address this, three experiments are designed corresponding to three research questions.

---

## Research Questions

1. **How does trajectory initialization affect the accuracy of arc-cost estimates used by the MILP in the VRTPP-PR framework?**

2. **How does sensitivity to initialization in Lambert-based trajectory optimization propagate across sequential mission legs in a multi-asteroid routing problem?**

3. **How do improvements in trajectory initialization influence mission-level outcomes, including routing decisions, convergence behavior, and computational efficiency in the VRTPP-PR framework?**

---

## Experiment 1: Arc-Cost Matrix Comparison

### Objective
Evaluate how initialization affects the **Δv / mass-ratio matrix** used by the MILP.

### Method
- Compute arc costs using:
  - Baseline model (single Hohmann seed)
  - Proposed model (TA-grid + multi-start seeds)
- Use identical asteroid sets and mission parameters

### Metrics

| Metric | Description |
|------|------------|
| Mean Δv difference | Average change in arc cost |
| Max Δv difference | Worst-case discrepancy |
| % arcs improved | Fraction where proposed method finds lower Δv |
| Rank changes | Changes in ordering of lowest-cost arcs |
| Route-relevant arc changes | Differences in arcs likely used by MILP |

### Output
- Heatmap of Δv differences between models
- Summary statistics table

### Purpose
Determines whether initialization changes the **cost landscape seen by the routing solver**.

---

## Experiment 2: Initialization Sensitivity and Propagation

### Objective
Evaluate how initialization sensitivity affects **multi-leg mission trajectories**.

### Method
1. Select a fixed route from MILP output
2. Solve sequential NLP twice:
   - Baseline initialization
   - Proposed initialization

### Metrics

| Metric | Description |
|------|------------|
| Departure time per leg | Shows timing differences |
| Transfer time per leg | Captures trajectory variation |
| Δv per leg | Cost differences |
| Arrival time per node | Schedule propagation |
| Total route Δv | Overall mission cost |

### Output
- Timeline comparison plots
- Table of trajectory parameters per leg

### Purpose
Demonstrates that **initialization errors propagate across mission legs**, affecting downstream feasibility and cost.

---

## Experiment 3: Full VRTPP-PR System Evaluation

### Objective
Evaluate impact of initialization on **routing and mission-level outcomes**.

### Method
- Run both models:
  - Baseline (paper)
  - Proposed (our_model)
- Use identical random asteroid sets
- Evaluate across varying problem sizes:
  - Number of refueling asteroids (n_r)
  - Number of mining asteroids (n_m)

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
- Comparative results table (existing dataset)
- Plots of:
  - Mining asteroids vs. model
  - Runtime vs. problem size
  - Convergence behavior

### Purpose
Evaluates how initialization affects **end-to-end system performance**, not just trajectory quality.

---

## Summary

The proposed evaluation framework isolates the impact of initialization at three levels:

1. **Arc level** → accuracy of cost estimates
2. **Trajectory level** → sensitivity and propagation across mission legs
3. **System level** → routing decisions, convergence, and mission outcomes

This multi-level approach ensures that improvements are assessed in the **context of asteroid mining logistics**, rather than trajectory optimization in isolation.
