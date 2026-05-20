# Verification Suite Results
_Generated: 2026-05-20 13:32_

---

## Experiment 1: Arc-Cost Matrix Comparison

Initialization strategy: **Baseline** = single Hohmann seed at T_d=0;  
**Proposed** = TA-grid (16 true-anomaly samples) + distance-corrected T_t seeds.

### Summary metrics

| Metric | Value |
|--------|-------|
| Arcs compared | 186 |
| Mean ΔV diff (proposed − paper) | -1.371 km/s |
| Max \|ΔV diff\| | 17.613 km/s |
| % arcs improved by proposed | 50.0% |
| % arcs where paper was better | 50.0% |
| Rank changes across destinations | 36 |

### Canonical route arcs (Earth → FG3 → Bennu → Earth)

| Arc | Baseline ΔV (km/s) | Proposed ΔV (km/s) | Δ (km/s) |
|-----|-------------------|-------------------|----------|
| Earth → 1996 FG3 | 6.609 | 6.686 | +0.077 |
| 1996 FG3 → 101955 Bennu | 7.261 | 7.790 | +0.529 |
| 101955 Bennu → Earth | 11.106 | 11.378 | +0.273 |

### Eccentricity gap (Earth → body arcs, sorted by eccentricity)

| Body | Eccentricity | Baseline ΔV (km/s) | Proposed ΔV (km/s) | Gap (B−P, km/s) |
|------|-------------|-------------------|-------------------|-----------------|
| 101955 Bennu | 0.020 | 9.423 | 10.633 | -1.210 |
| 1989 ML | 0.137 | 10.567 | 8.346 | +2.221 |
| 162173 Ryugu | 0.191 | 5.294 | 6.629 | -1.335 |
| 2001 CC21 | 0.219 | 10.480 | 5.341 | +5.140 |
| 1943 Anteros | 0.256 | 6.281 | 5.822 | +0.459 |
| 1996 FG3 | 0.350 | 6.609 | 6.686 | -0.077 |
| 2001 SG10 | 0.425 | 22.860 | 8.521 | +14.339 |

---

## Experiment 2: Initialization Sensitivity and Propagation

Fixed route: **Earth → 1996 FG3 → 101955 Bennu → Earth** (paper Table 5 route).  
Each leg is cold-started (T_t_prev=None), invoking each model's own init logic.

### Per-leg trajectory parameters

| Leg | Model | T_d (TU) | T_t (TU) | ΔV (km/s) | T_arrival (TU) |
|-----|-------|----------|----------|-----------|----------------|
| Earth → FG3 | Baseline | 0.087 | 6.257 | 9.506 | 6.344 |
| | Proposed | 0.000 | 4.047 | 10.312 | 4.047 |
| FG3 → Bennu | Baseline | 9.090 | 4.587 | 12.394 | 13.677 |
| | Proposed | 4.108 | 4.758 | 9.892 | 8.867 |
| Bennu → Earth | Baseline | 17.613 | 6.803 | 8.171 | 24.416 |
| | Proposed | 9.237 | 8.519 | 9.850 | 17.756 |

### Total route ΔV

| Model | Total ΔV (km/s) |
|-------|----------------|
| Baseline | 30.071 |
| Proposed | 30.054 |
| Improvement | +0.017 km/s (+0.1%) |

---

## Output files

| File | Description |
|------|-------------|
| `exp1_dv_heatmap.png` | Heatmap of ΔV differences (proposed − baseline) per body pair |
| `exp1_summary_table.png` | Summary metrics table for Exp 1 |
| `exp1_eccentricity_gap.png` | ΔV gap vs. destination eccentricity (Exp 1b) |
| `exp2_timeline.png` | Mission timeline comparison (horizontal bar chart) |
| `exp2_leg_table.png` | Per-leg parameter table for Exp 2 |
