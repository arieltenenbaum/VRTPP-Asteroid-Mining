# VRTPP-PR: Asteroid Mining Routing & Trajectory Optimizer

Implementation of the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) for near-Earth asteroid mining.

**Paper:** Choi & Ho, "Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization," AIAA SciTech 2026.

## Target Result

The optimizer should find: **Earth → 1996 FG3 → 101955 Bennu → Earth**

| Segment | Δv [km/s] | Transfer Time [TU] |
|---|---|---|
| Earth → FG3 | 9.51 | 6.26 |
| FG3 → Bennu | 7.32 | 7.06 |
| Bennu → Earth | 8.17 | 6.81 |

## Requirements

- Python 3.8+, NumPy, SciPy, Matplotlib
- Gurobi optimizer (licensed)

## Usage

Open `VRTPP_PR_Optimization.ipynb` in Jupyter and run all cells top-to-bottom.

## Context

See `HANDOVER.md` for full project context, change log, known issues, and next steps.
