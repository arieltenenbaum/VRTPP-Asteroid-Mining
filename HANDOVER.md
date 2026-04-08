# VRTPP-PR Handover Document
**Project:** Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization  
**Last Updated:** 2026-04-08  
**Purpose:** Living context document — update this file every session to record what changed, why, and what state the model is in.

---

## 1. What This Project Is

This is a Python/Jupyter implementation of the **VRTPP-PR** (Vehicle Routing and Trajectory Problem with Profits and Partial Refueling) algorithm from:

> **"Optimal Routing and Trajectory Planning for Asteroid Mining with Partial In-Situ Resource Utilization"**  
> Euihyeon Choi and Koki Ho, Georgia Institute of Technology  
> AIAA SciTech 2026 Forum, January 12-16, 2026, Orlando, FL  
> DOI: 10.2514/6.2026-2787

The goal is to replicate the paper's results exactly, then extend the model.

---

## 2. The Paper's Ground Truth (DO NOT DEVIATE FROM THIS)

### What the paper proves is optimal (Table 5 — the target result):

| Trajectory Segment | Departure Time [TU] | Transfer Time [TU] | Δv [km/s] | Initial Mass [kg] | Final Mass [kg] |
|---|---|---|---|---|---|
| **Earth → 1996 FG3** | 0.09 | 6.26 | 9.51 | 13,151.75 | 1,577.88 |
| **FG3 → 101955 Bennu** | 8.83 | 7.06 | 7.32 | 1,587.88 | 310.00 |
| **Bennu → Earth** | 17.59 | 6.81 | 8.17 | 1,917.42 | 310.00 |

**Mission summary (Table 4):**
- Initial propellant mass: **12,851.747 kg**
- Total refueling mass: **1,607.417 kg**
- Number of vehicles used: **1**
- Number of mining asteroids visited: **1** (FG3)
- Iterations to convergence: **10**
- Computation time: **10.726 seconds**

### Why this route makes physical sense:
- FG3's orbit closely approaches Earth → low energy departure
- Bennu has a slightly larger orbit than Earth → fuel-efficient refueling before return
- The spacecraft arrives at both Bennu and the final Earth return with only dry mass + mined mass (310 kg = 300 kg dry + 10 kg mined), meaning all propellant is consumed at those arrival points
- Without refueling at Bennu, Earth return is **infeasible**

---

## 3. Problem Parameters (Table 2 — Fixed Reference)

| Parameter | Value | Units |
|---|---|---|
| Gravitational parameter of Sun | 1.327 × 10¹¹ | km³/s² |
| Gravitational parameter of Earth | 3.986 × 10⁵ | km³/s² |
| Canonical Distance Unit (AU) | 1.496 × 10⁸ | km |
| Canonical Time Unit (TU) | 58.132 | days |
| Specific impulse (Isp) | 457 | s |
| Max spacecraft count (n_bv) | 3 | — |
| Max refueling visits (n_rv) | 3 | — |
| Mining mass per asteroid | 10 | kg |
| Spacecraft dry mass | 300 | kg |
| Max spacecraft mass | 20,000 | kg |
| Max payload capacity | 30 | kg |
| Parking orbit radius (Earth) | 7,000 | km |
| Mining/refueling service time | 2 | days |
| Profit per asteroid | 10 | — |
| Weighted factor (λ) | 5 × 10⁻⁵ | kg⁻¹ |

---

## 4. Celestial Bodies (Table 3 — Heliocentric Orbital Elements at Epoch 2461000.5)

| Type | Name | a [AU] | e | i [deg] | Ω [deg] | ω [deg] | M₀ [deg] |
|---|---|---|---|---|---|---|---|
| Base | Earth | 1.0009 | 0.0173 | 0.0032 | 171.7283 | 289.5838 | 318.5855 |
| Refueling | 162173 Ryugu | 1.1909 | 0.1911 | 5.8666 | 251.2915 | 211.6168 | 270.6594 |
| Refueling | 101955 Bennu | 1.1260 | 0.0204 | 6.0328 | 1.9690 | 66.4073 | 267.4691 |
| Mining | 2001 SG10 | 1.4487 | 0.4246 | 4.2568 | 184.8938 | 101.6706 | 340.8908 |
| Mining | 1989 ML | 1.2728 | 0.1369 | 4.3791 | 104.2721 | 183.6253 | 121.5130 |
| Mining | **1996 FG3** | 1.0548 | 0.3501 | 1.9727 | 299.4710 | 24.0570 | 36.6506 |
| Mining | 2001 CC21 | 1.0321 | 0.2192 | 4.8086 | 75.3575 | 179.4026 | 140.7404 |
| Mining | 1943 Anteros | 1.4305 | 0.2559 | 8.7077 | 246.2935 | 338.4366 | 260.3741 |

**Note:** The paper uses n_r = 2 refueling asteroids (Ryugu, Bennu) and n_m = 5 mining asteroids (SG10, ML, FG3, CC21, Anteros) for the case study.

---

## 5. Algorithm Architecture (How the Code Works)

The solution method decouples the MINLP into two alternating subproblems:

```
Initialize mass ratios (NLP on all pairs, zero departure time + Hohmann TOF as initial guess)
    ↓
LOOP until convergence (Frobenius norm of ΔΔv / max(Δv_old) < ε_c = 10⁻³):
    ├── Step 1: MILP with FIXED mass ratios → optimal route + refueling amounts
    └── Step 2: NLP (Lambert + trust-region) for EACH segment of that route → updated mass ratios
```

**Key equations:**
- **Objective (Eq. 10):** Maximize Σ profits − λ × total fuel consumed
- **Mass ratio (Eq. in text):** m_ij = exp(−Δv_ij / g₀Isp)
- **Earth Δv correction (Eq. 48):** Δv_act = √(Δv²_heli + 2μ_e/r₀) − √(μ_e/r₀)
- **NLP convergence (Eq. 47):** ‖Δv_old − Δv_new‖_F / max(Δv_old) ≤ 10⁻³

---

## 6. Code Structure (VRTPP_PR_Optimization.ipynb)

| Cell | Section | Description |
|---|---|---|
| 2 | Imports | numpy, scipy, gurobipy, warnings |
| 4 | OrbitalBody | Kepler equation solver, position/velocity at time t |
| 5 | LambertSolver | Universal variable Lambert's problem with Stumpff functions |
| 7 | Asteroid Data | All 8 bodies instantiated (Table 3 values) |
| 9 | Parameters | Dataclass with all Table 2 values |
| 11 | build_index_sets | Equations 1-9: builds B₀, Bᵥ, Bs, Be, R₀, Rᵥ, R, M, V, N |
| 12 | Node mapping | Assigns bodies to node indices |
| 14 | TrajectoryOptimizer | NLP: compute_delta_v, optimize_segment (L-BFGS-B) |
| 16 | Verification | Checks computed Δv against Table 5 expected values |
| 18 | build_milp | Full MILP construction with Gurobi (Eqs. 10-42) |
| 20 | extract_routes | Reads binary x variables to recover route sequence |
| 21 | initialize_mass_ratios | Grid + NLP initialization per Section IV.A |
| 24 | solve_vrtpp_pr | Main iterative loop: MILP → NLP → check convergence |
| 26 | Run optimization | Calls solve_vrtpp_pr with case study params |
| 27 | Diagnostics | Prints all mass ratios and transfer times |
| 29 | Results display | Prints final solution table |
| 31 | Visualization | Matplotlib route plot |

---

## 7. Known Issues & Current Status

### Primary Issue: Solution Not Matching Table 5
The optimizer runs but does **not** produce `Earth → FG3 → Bennu → Earth`. The results display cell (Cell 29) shows no output, indicating `solution = None` or `solution['routes']` is empty.

**Suspected causes (to debug in order):**
1. **MILP infeasibility:** Mass ratio constraints (Eqs. 38-42) may be too tight given initialization values, causing the MILP to have no feasible routes
2. **Index set offset bug:** Cell 11 `build_index_sets` has non-standard offsets compared to the paper's Eqs. 1-9 — this was manually corrected at some point but may still be misaligned
3. **NLP returning 100.0 Δv:** The trajectory optimizer returns a penalty value (100.0 km/s) on failure, producing mass ratios near zero that kill the MILP
4. **Single-spacecraft constraint:** A manual constraint was added to `build_milp` limiting total spacecraft to 1 — this could interact badly with the virtual node structure

### Secondary Issues
- Cell 16 verification: Δv errors may be >15% for some segments, indicating the Earth Δv correction (Eq. 48) or Lambert solver may be slightly off
- The `initialize_mass_ratios` function uses a grid scan (step = 1 TU), which may miss narrow launch windows

---

## 8. Change Log

### Session: 2026-04-08 (Initial Repository Setup)
**Status at start:** Model runs without crashing. Solution is None or routes are empty. Verification cell (Cell 16) exists but output not captured.

**What exists:**
- Full MILP-NLP iterative solver in Python/Jupyter
- Gurobi licensed and working on Ariel's machine (miniconda3)
- MATLAB reference file (`VRTPP_PR_Optimization.m`) also present
- All orbital elements from Table 3 hardcoded correctly
- All parameters from Table 2 implemented in `Parameters` dataclass

**What was changed in prior sessions (reconstructed from code state):**
- `build_index_sets` (Cell 11): `Be` start was corrected from `n_bv` to `n_bv+1` to prevent overlap with `Bs`. `k_prime` offset updated accordingly.
- `build_milp` (Cell 18): Added explicit `model.addConstr(total spacecraft <= 1)` to match case study result
- `TrajectoryOptimizer.optimize_segment` (Cell 14): Multi-start added (T_t = 2.0, 6.0, 10.0 TU alternatives) on top of Hohmann initial guess; changed from trust-region (paper) to L-BFGS-B
- `initialize_mass_ratios` (Cell 21): Changed from simple Hohmann estimate to grid+NLP scan

**No changes made this session** — repository initialized for version control.

---

## 9. What Needs to Be Done (In Priority Order)

### Phase 1: Debug to Match Paper Results
- [ ] Run Cell 16 and capture output — verify Δv errors are <15% for all 3 legs
- [ ] Add diagnostic print statements inside `solve_vrtpp_pr` to see: MILP status, mass ratios at each iteration, route found at each iteration
- [ ] If MILP is infeasible: relax MIPGap, print infeasibility certificate, check constraint bounds
- [ ] Verify `k_prime` mapping is consistent between `build_index_sets` and `build_milp`
- [ ] Compare index sets (Bs, Be, R, M) against paper Eqs. 1-9 by printing them and checking manually

### Phase 2: Add Time Windows to MILP
- Add time window constraints on departure times: T_d_min ≤ T_d ≤ T_d_max per node
- This extends Eq. 44 (NLP lower bound) into the MILP

### Phase 3: Multi-Objective Optimization
- Implement Pareto front: sweep λ from 0 to large values
- Plot profit vs fuel trade-off curve

### Phase 4: Tighter Trajectory Integration
- Replace L-BFGS-B with trust-region (as in paper)
- Consider global optimizer (grid search) for Δv initialization
- Couple mining time (T_service) to mining mass amount

---

## 10. How to Run

**Environment:** Ariel's machine, miniconda3  
**Solver:** Gurobi (licensed, cannot be run remotely by Claude)

```bash
cd ~/Downloads/VRTPP-Asteroid-Mining
jupyter lab VRTPP_PR_Optimization.ipynb
# Run all cells top-to-bottom
# Key output cells: 16 (verification), 26 (main run), 29 (results)
```

**Workflow for debugging sessions:**
1. Run all cells
2. Copy any error messages or cell outputs and paste to Claude
3. Claude edits the notebook file directly
4. Ariel re-runs in Jupyter

---

## 11. Files in This Repository

| File | Description |
|---|---|
| `VRTPP_PR_Optimization.ipynb` | Main implementation (Python + Gurobi) |
| `HANDOVER.md` | This document — update with every commit |
| `.gitignore` | Ignores checkpoints, .DS_Store, Gurobi logs |

**The source paper PDF is NOT in this repo** (copyright protected). Keep it locally at:  
`~/Downloads/Optimal Routing and Trajectory Planning for Asteroid Mining.pdf`

---

## 12. Version Control Strategy

Commit **frequently** — after each meaningful change, not just at the end of a session. The goal is that every commit represents a recoverable, meaningful state so you can roll back to any point between iterations.

### When to commit:
- After each code change Claude makes (before you run it)
- After a debug attempt — whether it worked or not
- Any time you want to "save" the current state before trying something risky

### Commit commands:
```bash
cd ~/Downloads/VRTPP-Asteroid-Mining
git add VRTPP_PR_Optimization.ipynb HANDOVER.md
git commit -m "short description of what changed"
git push origin main
```

### To roll back to a previous state:
```bash
git log --oneline          # see all commits
git checkout <hash> -- VRTPP_PR_Optimization.ipynb   # restore a specific file
```

### Update HANDOVER.md with every commit — add to Section 8:
```
### YYYY-MM-DD — [short label, e.g. "debug MILP mass constraints"]
**Changed:** Cell XX — [what was changed]
**Why:** [reason]
**Result:** [output / error / improvement]
**Status:** [working / broken / partial]
```
