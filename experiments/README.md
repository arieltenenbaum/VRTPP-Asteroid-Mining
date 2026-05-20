# Experiment Results

Comparison between the paper (Choi & Ho, AIAA SciTech 2026) and our extended model.

**How to add results:** Edit `results.csv` — fill in the `our_model` rows as you run experiments. Computation times are recorded but not used for comparison (different hardware). The `notes` column is free-text for anything worth flagging (e.g. "non-convergence reason", "parameter change").

## Column Reference

| Column | Description |
|--------|-------------|
| `model` | `paper` or `our_model` |
| `n_r` | Number of refueling asteroids |
| `n_m` | Number of candidate mining asteroids |
| `iterations_min/max/mean` | MILP-NLP iterations until convergence across all problems in the batch |
| `time_min/max/mean_sec` | Wall-clock computation time in seconds |
| `mining_asteroids_min/max/mean` | Number of asteroids selected for mining in the optimal solution |
| `trivial_problems` | Problems that converged in 1 iteration (trivially solved) |
| `non_converged_problems` | Problems that hit the iteration limit without converging |
| `mip_gap_final_min/max/mean` | Gurobi MIPGap at the final MILP call of each instance (0.0 = proven optimal) |
| `notes` | Free-text annotation — includes instance count, seed range, MIPGap, and TimeLimit |

## Experiment Settings Log

| Configs | N_INSTANCES | Seeds | MIPGap | TimeLimit | Reason for change |
|---------|-------------|-------|--------|-----------|-------------------|
| our_model (1,4) and (1,6) | 5 | 42–46 | 0.0 | 30 s | Initial setting |
| our_model (1,8) | 5 | 42–46 | 0.0 | 30 s | Ran before instance reduction |
| our_model n_r=1 (1,8) onward | 3 | 42–44 | 0.0 | 30 s | Reduced instances to shorten runtime |
| our_model n_r=2 | 3 | 42–44 | 0.05 | 30 s | Relaxed MIP gap to speed up larger configs |
| our_model n_r=3 | 3 | 42–44 | 0.10 | 30 s | Further relaxed MIP gap for largest configs |

## Paper Results (Table 6, VRTPP-PR)

| n_r | n_m | Iter min | Iter max | Iter mean | Time min | Time max | Time mean | Mine min | Mine max | Mine mean | Trivial | Non-conv |
|-----|-----|----------|----------|-----------|----------|----------|-----------|----------|----------|-----------|---------|----------|
| 1 | 4 | 3 | 24 | 11.6 | 0.68 | 10.36 | 4.89 | 1 | 3 | 1.9 | 2 | 1 |
| 1 | 6 | 8 | 32 | 15.0 | 4.07 | 61.05 | 24.74 | 1 | 4 | 2.9 | 0 | 2 |
| 1 | 8 | 10 | 49 | 19.3 | 15.24 | 191.56 | 52.44 | 2 | 5 | 3.7 | 1 | 0 |
| 1 | 10 | 5 | 29 | 15.0 | 16.19 | 423.76 | 228.68 | 1 | 7 | 4.4 | 1 | 1 |
| 2 | 4 | 15 | 31 | 22.9 | 11.09 | 1467.53 | 253.98 | 1 | 4 | 2.0 | 1 | 0 |
| 2 | 6 | 8 | 27 | 19.4 | 97.38 | 1348.61 | 411.66 | 2 | 6 | 3.9 | 0 | 1 |
| 2 | 8 | 14 | 36 | 26.6 | 207.65 | 2181.20 | 1102.81 | 2 | 7 | 4.2 | 0 | 1 |
| 2 | 10 | 15 | 39 | 26.1 | 568.26 | 3527.53 | 1675.46 | 4 | 6 | 4.9 | 0 | 2 |
| 3 | 4 | 11 | 35 | 20.6 | 299.96 | 3226.16 | 1461.23 | 1 | 4 | 2.9 | 0 | 0 |
| 3 | 6 | 9 | 40 | 26.6 | 906.82 | 3015.09 | 1765.62 | 1 | 5 | 3.3 | 0 | 3 |
| 3 | 8 | 22 | 48 | 34.6 | 1658.57 | 4170.14 | 2798.04 | 2 | 7 | 4.4 | 0 | 3 |
| 3 | 10 | 25 | 46 | 35.1 | 2115.07 | 4647.68 | 3052.03 | 2 | 7 | 4.1 | 0 | 3 |

## Our Model Results

*(Fill in as experiments are run)*

| n_r | n_m | Iter min | Iter max | Iter mean | Time min | Time max | Time mean | Mine min | Mine max | Mine mean | Trivial | Non-conv | Notes |
|-----|-----|----------|----------|-----------|----------|----------|-----------|----------|----------|-----------|---------|----------|-------|
| 1 | 4 | | | | | | | | | | | | |
| 1 | 6 | | | | | | | | | | | | |
| 1 | 8 | | | | | | | | | | | | |
| 1 | 10 | | | | | | | | | | | | |
| 2 | 4 | | | | | | | | | | | | |
| 2 | 6 | | | | | | | | | | | | |
| 2 | 8 | | | | | | | | | | | | |
| 2 | 10 | | | | | | | | | | | | |
| 3 | 4 | | | | | | | | | | | | |
| 3 | 6 | | | | | | | | | | | | |
| 3 | 8 | | | | | | | | | | | | |
| 3 | 10 | | | | | | | | | | | | |
