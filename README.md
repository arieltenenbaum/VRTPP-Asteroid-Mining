# VRTPP-PR: Asteroid Mining Routing & Trajectory Optimizer

> **Branch: `verification-suite`** — Scalability experiments and optimizer verification against paper Table 6.

This branch runs the MILP–NLP optimizer from `main` across a range of problem sizes (number of refueling and mining asteroids) and records results for comparison with Choi & Ho (AIAA SciTech 2026), Table 6.

**Reference paper:** Choi & Ho, *"Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization,"* AIAA SciTech 2026.

---

## Repository Branches

| Branch | Purpose |
|--------|---------|
| `main` | Core MILP-NLP optimizer with NLP warm-start initialization |
| **`verification-suite`** (this branch) | Scalability experiments comparing our model against paper Table 6 |
| `bang-ahn-grid-init` | Experimental: adaptive grid sizing based on Bang & Ahn two-phase framework |

---

## Paper Target Route

| Segment | Δv [km/s] | Transfer Time [TU] |
|---|---|---|
| Earth → 1996 FG3 | 9.51 | 6.26 |
| FG3 → 101955 Bennu | 7.32 | 7.06 |
| Bennu → Earth | 8.17 | 6.81 |

---

## What This Branch Does

The verification suite runs the optimizer over all combinations of:

- **n_r** (refueling asteroids): 1, 2, 3
- **n_m** (mining asteroid candidates): 4, 6, 8, 10

For each configuration it records iteration counts, wall-clock time, and the number of asteroids selected for mining, matching the schema in paper Table 6.

### Optimizer Health Checks (Section 14)

`VRTPP_PR_Optimization.ipynb` includes five independent checks:

| Check | Status | Notes |
|-------|--------|-------|
| Kepler equation residuals | Pass | Machine-precision convergence on all bodies |
| MILP optimality gap | Warning (3%) | Caused by NLP local-minimum errors on two legs |
| Pork chop NLP vs grid minimum | **Two legs off by 2–4 km/s** | Root cause: initialization grid too coarse in T_t |
| Brute-force route enumeration | Skipped (4-body route) | Re-run after fixing initialization |
| Perturbation sensitivity | Pass (T_d direction only) | Does not probe T_t direction |

See `VERIFICATION.md` for the full diagnosis and recommended fixes.

---

## Files

| File | Description |
|------|-------------|
| `VRTPP_PR_Optimization.ipynb` | Main optimizer + Section 14 verification suite |
| `VRTPP-PaperModel.ipynb` | Paper replication (results differ from paper) |
| `experiments/experiment_scalability.ipynb` | Scalability experiment runner |
| `experiments/results.csv` | Results table (fill in as experiments are run) |
| `VERIFICATION.md` | Full write-up of verification findings and next actions |

---

## Running the Experiments

1. Open `experiments/experiment_scalability.ipynb` in Jupyter.
2. Run all cells. Each configuration (n_r, n_m) runs 10 random problem instances.
3. Results append automatically to `experiments/results.csv`.
4. Compare against paper Table 6 values in `experiments/README.md`.

> **Gurobi license required.** Experiments must run locally.

---

## Requirements

- Python 3.8+, NumPy, SciPy, Matplotlib
- **Gurobi optimizer** with a valid license

```bash
pip install numpy scipy matplotlib gurobipy
```

---

## Documentation

| Document | Contents |
|----------|----------|
| `VERIFICATION.md` | Optimizer verification findings (checks 14.1–14.5) |
| `experiments/README.md` | Column definitions and paper Table 6 reference values |
| `MODEL_COMPARISON_AND_VALIDATION.md` | Broader model vs. paper comparison |
| `HANDOVER_2026-04-27.md` | Latest project status, known issues, next steps |

