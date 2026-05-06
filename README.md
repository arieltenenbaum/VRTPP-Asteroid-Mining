# VRTPP-PR: Asteroid Mining Routing & Trajectory Optimizer

> **Branch: `main`** — Primary optimizer with NLP warm-start and MILP–NLP iterative solver.

Implementation of the Vehicle Routing and Trajectory Problem with Profits and Partial Refueling (VRTPP-PR) for near-Earth asteroid mining.

**Reference paper:** Choi & Ho, *"Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization,"* AIAA SciTech 2026.

---

## Repository Branches

| Branch | Purpose |
|--------|---------|
| **`main`** (this branch) | Core MILP–NLP optimizer with NLP warm-start initialization |
| `verification-suite` | Scalability experiments comparing our model against paper Table 6 |
| `bang-ahn-grid-init` | Experimental: adaptive grid sizing based on Bang & Ahn two-phase framework |

---

## Paper Target Route

| Segment | Δv [km/s] | Transfer Time [TU] |
|---|---|---|
| Earth → 1996 FG3 | 9.51 | 6.26 |
| FG3 → 101955 Bennu | 7.32 | 7.06 |
| Bennu → Earth | 8.17 | 6.81 |

Our optimizer currently finds a **better route** than this reference (lower total Δv via a different asteroid sequence), using NLP warm-starting to avoid local minima.

---

## How the Solver Works

The optimizer alternates between two phases until convergence:

1. **MILP phase** — Gurobi solves the discrete routing problem (which asteroids to visit, in what order) given current Δv estimates for all arcs.
2. **NLP phase** — `scipy.optimize` refines the transfer timing (departure time T_d, transfer time T_t) for each leg of the chosen route, using Lamberts problem to compute actual Δv.

**Initialization:** `initialize_mass_ratios` pre-computes Δv estimates for all possible arcs via a coarse (T_d, T_t) grid scan followed by L-BFGS-B refinement. See `INITIALIZATION_EXPLAINED.md` for a detailed walkthrough.

**Warm-start:** Each NLP call seeds from the previous iterations (T_d, T_t) solution, and Gurobi is seeded with the previous MILP integer solution. This stabilizes convergence across the ~22 iterations typically required.

---

## Known Limitation

The coarse initialization grid (T_t up to 13 TU in 2 TU steps) can miss the global Δv minimum for some body pairs. The `bang-ahn-grid-init` branch addresses this with orbit-period-scaled adaptive grids. See `VERIFICATION.md` (on `verification-suite`) for the full diagnosis.

---

## Notebooks

| Notebook | Description |
|----------|-------------|
| `VRTPP_PR_Optimization.ipynb` | **Main optimizer** — run this for route optimization |
| `VRTPP-PaperModel.ipynb` | Paper replication attempt (results differ; see handover docs) |

---

## Requirements

- Python 3.8+, NumPy, SciPy, Matplotlib
- **Gurobi optimizer** with a valid license (must run locally)

```bash
pip install numpy scipy matplotlib gurobipy
```

---

## Usage

Open `VRTPP_PR_Optimization.ipynb` in Jupyter and run all cells top-to-bottom.

---

## Documentation

| Document | Contents |
|----------|----------|
| `INITIALIZATION_EXPLAINED.md` | How the grid scan, L-BFGS-B refiner, and warm-start work |
| `MODEL_COMPARISON_AND_VALIDATION.md` | Comparison between our model and the paper |
| `HANDOVER_2026-04-27.md` | Latest project status, known issues, next steps |
| `HANDOVER_2026-04-*.md` | Earlier handover notes (chronological) |

