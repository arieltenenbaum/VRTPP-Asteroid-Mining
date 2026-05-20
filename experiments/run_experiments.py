"""
run_experiments.py – VRTPP-PR scalability experiments.

Core implementation extracted verbatim from VRTPP_PR_Optimization.ipynb
(periapsis-init branch). Do not edit the orbital-mechanics/solver sections
manually; sync from notebook instead.

Run from the repo root:
    python3 experiments/run_experiments.py              # all missing configs
    python3 experiments/run_experiments.py --config 1 4 # single config

Results written to experiments/results.csv incrementally.
"""

import argparse
import os, sys, time, csv, statistics, random, warnings
import numpy as np
from scipy.optimize import minimize, Bounds
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import gurobipy as gp
from gurobipy import GRB

warnings.filterwarnings('ignore')

# ── File paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(SCRIPT_DIR, "results.csv")
README_PATH = os.path.join(SCRIPT_DIR, "README.md")

# ── Configurations & settings ─────────────────────────────────────────────────
ALL_CONFIGS = [
    (1, 4), (1, 6), (1, 8),
    (2, 4), (2, 6), (2, 8),
    (3, 4), (3, 6), (3, 8),
]
N_INSTANCES     = 5
BASE_SEED       = 42
MILP_TIME_LIMIT = 30.0
MILP_MIP_GAP    = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Core implementation — extracted verbatim from VRTPP_PR_Optimization.ipynb
# (periapsis-init branch). Sync from notebook after any relevant commit.
# ─────────────────────────────────────────────────────────────────────────────

# Cell 4 — OrbitalBody
class OrbitalBody:
    """Celestial body with orbital elements."""

    def __init__(self, name: str, a: float, e: float, i: float,
                 Omega: float, omega: float, M0: float, epoch: float = 0.0):
        self.name = name
        self.a = a
        self.e = e
        self.i = np.deg2rad(i)
        self.Omega = np.deg2rad(Omega)
        self.omega = np.deg2rad(omega)
        self.M0 = np.deg2rad(M0)
        self.epoch = epoch

    def position_at_time(self, t: float, mu: float = 1.0) -> np.ndarray:
        n = np.sqrt(mu / self.a**3)
        M = self.M0 + n * (t - self.epoch)
        E = self._solve_kepler(M, self.e)
        nu = 2 * np.arctan2(np.sqrt(1 + self.e) * np.sin(E / 2),
                            np.sqrt(1 - self.e) * np.cos(E / 2))
        r_mag = self.a * (1 - self.e * np.cos(E))
        R = self._rotation_matrix()
        return R @ np.array([r_mag * np.cos(nu), r_mag * np.sin(nu), 0])

    def velocity_at_time(self, t: float, mu: float = 1.0) -> np.ndarray:
        n = np.sqrt(mu / self.a**3)
        M = self.M0 + n * (t - self.epoch)
        E = self._solve_kepler(M, self.e)
        nu = 2 * np.arctan2(np.sqrt(1 + self.e) * np.sin(E / 2),
                            np.sqrt(1 - self.e) * np.cos(E / 2))
        h = np.sqrt(mu * self.a * (1 - self.e**2))
        R = self._rotation_matrix()
        return R @ np.array([-(mu / h) * np.sin(nu), (mu / h) * (self.e + np.cos(nu)), 0])

    def _solve_kepler(self, M: float, e: float, tol: float = 1e-10) -> float:
        E = M if e < 0.8 else np.pi
        for _ in range(50):
            f = E - e * np.sin(E) - M
            f_prime = 1 - e * np.cos(E)
            E_new = E - f / f_prime
            if abs(E_new - E) < tol:
                return E_new
            E = E_new
        return E

    def _rotation_matrix(self) -> np.ndarray:
        c_O, s_O = np.cos(self.Omega), np.sin(self.Omega)
        c_i, s_i = np.cos(self.i), np.sin(self.i)
        c_w, s_w = np.cos(self.omega), np.sin(self.omega)
        return np.array([
            [c_O * c_w - s_O * c_i * s_w, -c_O * s_w - s_O * c_i * c_w, s_O * s_i],
            [s_O * c_w + c_O * c_i * s_w, -s_O * s_w + c_O * c_i * c_w, -c_O * s_i],
            [s_i * s_w, s_i * c_w, c_i]
        ])

    def time_at_true_anomaly_after(self, nu: float, t_start: float, mu: float = 1.0) -> float:
        """Return next time at or after t_start when body is at true anomaly nu [rad]."""
        E = 2 * np.arctan2(np.sqrt(1 - self.e) * np.sin(nu / 2),
                           np.sqrt(1 + self.e) * np.cos(nu / 2))
        M_target = (E - self.e * np.sin(E)) % (2 * np.pi)
        n = np.sqrt(mu / self.a**3)
        M_now = (self.M0 + n * (t_start - self.epoch)) % (2 * np.pi)
        dM = (M_target - M_now) % (2 * np.pi)
        return t_start + dM / n


# Cell 5 — LambertSolver
class LambertSolver:
    """Robust Lambert solver using universal variables with Stumpff functions."""

    def __init__(self, mu: float = 1.0):
        self.mu = mu

    def solve(self, r1_vec: np.ndarray, r2_vec: np.ndarray, tof: float,
              prograde: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        r1 = np.linalg.norm(r1_vec)
        r2 = np.linalg.norm(r2_vec)
        cos_dnu = np.clip(np.dot(r1_vec, r2_vec) / (r1 * r2), -1.0, 1.0)
        cross = np.cross(r1_vec, r2_vec)
        if prograde:
            dnu = np.arccos(cos_dnu) if cross[2] >= 0 else 2 * np.pi - np.arccos(cos_dnu)
        else:
            dnu = np.arccos(cos_dnu) if cross[2] < 0 else 2 * np.pi - np.arccos(cos_dnu)
        A = np.sin(dnu) * np.sqrt(r1 * r2 / (1 - cos_dnu))
        if abs(A) < 1e-14:
            raise ValueError("Degenerate Lambert problem")

        def C2(psi):
            if psi > 1e-6:   return (1 - np.cos(np.sqrt(psi))) / psi
            elif psi < -1e-6: return (np.cosh(np.sqrt(-psi)) - 1) / (-psi)
            else:             return 0.5

        def C3(psi):
            if psi > 1e-6:
                sp = np.sqrt(psi); return (sp - np.sin(sp)) / (psi * sp)
            elif psi < -1e-6:
                sp = np.sqrt(-psi); return (np.sinh(sp) - sp) / ((-psi) * sp)
            else: return 1.0 / 6.0

        psi_n, psi_up, psi_low = 0.0, 4 * np.pi**2, -4 * np.pi**2
        for _ in range(100):
            c2, c3 = C2(psi_n), C3(psi_n)
            y_n = r1 + r2 + A * (psi_n * c3 - 1) / np.sqrt(c2)
            if y_n < 0:
                for _ in range(2000):
                    psi_n += 0.1; c2, c3 = C2(psi_n), C3(psi_n)
                    y_n = r1 + r2 + A * (psi_n * c3 - 1) / np.sqrt(c2)
                    if y_n >= 0: break
                else:
                    raise ValueError("Lambert solver: could not find valid y_n")
            chi = np.sqrt(y_n / c2)
            tof_n = (chi**3 * c3 + A * np.sqrt(y_n)) / np.sqrt(self.mu)
            if abs(tof_n - tof) < 1e-8 * abs(tof): break
            if tof_n <= tof: psi_low = psi_n
            else:            psi_up  = psi_n
            dtof = (chi**3 * (C3(psi_n) - 3 * c3 * C2(psi_n) / (2 * c2)) / (2 * c2) +
                    (A / 8) * (3 * c3 * np.sqrt(y_n) / c2 + A / chi)) / np.sqrt(self.mu)
            if abs(dtof) > 1e-14:
                psi_new = psi_n + (tof - tof_n) / dtof
                psi_n = psi_new if psi_low <= psi_new <= psi_up else (psi_up + psi_low) / 2
            else:
                psi_n = (psi_up + psi_low) / 2
        f, g_dot = 1 - y_n / r1, 1 - y_n / r2
        g = A * np.sqrt(y_n / self.mu)
        if abs(g) < 1e-14:
            raise ValueError("Lambert solver: g is near zero")
        return (r2_vec - f * r1_vec) / g, (g_dot * r2_vec - r1_vec) / g


# Earth global — needed by build_node_mapping
earth = OrbitalBody("Earth", a=1.0009, e=0.0173, i=0.0032,
                    Omega=171.7283, omega=289.5838, M0=318.5855)


# Cell 9 — Parameters
@dataclass
class Parameters:
    """Problem parameters from Table 2."""
    mu_sun: float = 1.0
    mu_earth: float = 3.986e5
    g0: float = 9.81e-3
    m_dry: float = 300.0
    m_max: float = 20000.0
    q_max: float = 30.0
    I_sp: float = 457.0
    n_bv: int = 3
    n_rv: int = 3
    T_service: float = 2.0 / 58.132
    lambda_weight: float = 5e-5
    profit: float = 10.0
    mining_mass: float = 10.0
    r0_park: float = 7000.0
    AU_to_km: float = 1.496e8
    TU_to_sec: float = 58.132 * 86400


# Cell 11 — build_index_sets + build_node_mapping
def build_index_sets(params: Parameters, n_refuel: int, n_mine: int) -> Dict:
    """Build index sets (Equations 1-9)."""
    n_bv = params.n_bv
    n_rv = params.n_rv
    B0 = [0]
    Bv = list(range(1, n_bv + 1))
    Bs = list(range(0, n_bv + 1))
    Be = list(range(n_bv + 1, 2 * n_bv + 2))
    R0 = list(range(2 * n_bv + 2, 2 * n_bv + n_refuel + 2))
    Rv = list(range(2 * n_bv + n_refuel + 2, 2 * n_bv + n_refuel * n_rv + 2))
    R = R0 + Rv
    M = list(range(2 * n_bv + n_refuel * n_rv + 2,
                   2 * n_bv + n_refuel * n_rv + n_mine + 2))
    V = R + M
    N = Bs + Be + V
    k_prime = {k: k + n_bv + 1 for k in Bs}
    return {'B0': B0, 'Bv': Bv, 'Bs': Bs, 'Be': Be,
            'R0': R0, 'Rv': Rv, 'R': R, 'M': M, 'V': V, 'N': N,
            'k_prime': k_prime}


def build_node_mapping(sets: Dict, refueling_bodies: List, mining_bodies: List) -> Tuple[Dict, Dict]:
    """Map node indices to celestial bodies."""
    node_to_body, node_to_name = {}, {}
    for node in sets['Bs'] + sets['Be']:
        node_to_body[node] = earth
        node_to_name[node] = "Earth"
    for i, node in enumerate(sets['R']):
        b = refueling_bodies[i % len(refueling_bodies)]
        node_to_body[node] = b
        node_to_name[node] = b.name
    for i, node in enumerate(sets['M']):
        node_to_body[node] = mining_bodies[i]
        node_to_name[node] = mining_bodies[i].name
    return node_to_body, node_to_name


# Cell 14 — TrajectoryOptimizer
class TrajectoryOptimizer:
    """Optimizes trajectory for a single segment using Lambert's problem."""

    def __init__(self, params: Parameters):
        self.params = params
        self.lambert = LambertSolver(mu=params.mu_sun)

    def compute_delta_v(self, body_i: OrbitalBody, body_j: OrbitalBody,
                        T_d: float, T_t: float) -> float:
        r1 = body_i.position_at_time(T_d, self.params.mu_sun)
        r2 = body_j.position_at_time(T_d + T_t, self.params.mu_sun)
        v1_orbit = body_i.velocity_at_time(T_d, self.params.mu_sun)
        v2_orbit = body_j.velocity_at_time(T_d + T_t, self.params.mu_sun)
        try:
            v1_transfer, v2_transfer = self.lambert.solve(r1, r2, T_t, prograde=True)
        except Exception:
            return 100.0
        conversion = self.params.AU_to_km / self.params.TU_to_sec
        dv1_heli = np.linalg.norm(v1_transfer - v1_orbit) * conversion
        dv2_heli = np.linalg.norm(v2_orbit - v2_transfer) * conversion
        if body_i.name == "Earth":
            dv1 = self._earth_departure_dv((v1_transfer - v1_orbit) * conversion)
        else:
            dv1 = dv1_heli
        if body_j.name == "Earth":
            dv2 = self._earth_arrival_dv((v2_orbit - v2_transfer) * conversion)
        else:
            dv2 = dv2_heli
        return dv1 + dv2

    def _earth_departure_dv(self, v_inf: np.ndarray) -> float:
        v_inf_mag = np.linalg.norm(v_inf)
        v_park = np.sqrt(self.params.mu_earth / self.params.r0_park)
        return abs(np.sqrt(v_inf_mag**2 + 2 * self.params.mu_earth / self.params.r0_park) - v_park)

    def _earth_arrival_dv(self, v_inf: np.ndarray) -> float:
        v_inf_mag = np.linalg.norm(v_inf)
        v_park = np.sqrt(self.params.mu_earth / self.params.r0_park)
        return abs(np.sqrt(v_inf_mag**2 + 2 * self.params.mu_earth / self.params.r0_park) - v_park)

    def optimize_segment(self, body_i: OrbitalBody, body_j: OrbitalBody,
                         T_arrival_i: float, T_t_prev: float = None,
                         T_d_prev: float = None) -> Dict:
        from scipy.optimize import Bounds as ScipyBounds
        service = self.params.T_service if body_i.name != "Earth" else 0.0
        T_d_min = T_arrival_i + service
        a_transfer = (body_i.a + body_j.a) / 2
        T_t_hoh = np.pi * np.sqrt(a_transfer**3 / self.params.mu_sun)
        if T_t_prev is not None:
            T_t_init = T_t_prev
        else:
            T_t_candidates = np.arange(1.0, 14.0, 2.0)
            best_T_t, best_dv_scan = T_t_hoh, 1e9
            for T_t_cand in T_t_candidates:
                try:
                    dv_cand = self.compute_delta_v(body_i, body_j, T_d_min, T_t_cand)
                    if np.isfinite(dv_cand) and dv_cand < best_dv_scan:
                        best_dv_scan, best_T_t = dv_cand, T_t_cand
                except Exception:
                    pass
            T_t_init = best_T_t
        T_d_max = T_d_min + 5.0
        T_d_init = max(T_d_prev, T_d_min) if T_d_prev is not None else T_d_min
        T_d_init = min(T_d_init, T_d_max)
        x0 = np.array([T_d_init, max(T_t_init, 1e-5)], dtype=float)
        bounds = ScipyBounds([T_d_min, 1e-5], [T_d_max, 30.0])

        def objective(x):
            dv = self.compute_delta_v(body_i, body_j, x[0], x[1])
            return dv if np.isfinite(dv) else 1e6

        try:
            res = minimize(objective, x0=x0, method='trust-constr', bounds=bounds,
                           options={'maxiter': 500, 'verbose': 0, 'gtol': 1e-8, 'xtol': 1e-8})
            success = res is not None and np.isfinite(res.fun) and res.fun < 100.0
        except Exception:
            success, res = False, None

        if not success:
            return {'T_d': T_d_init, 'T_t': max(T_t_init, 1e-5), 'delta_v': 100.0,
                    'T_a': T_d_init + max(T_t_init, 1e-5), 'mass_ratio': 1e-10}

        T_d_opt, T_t_opt = res.x
        dv_opt = res.fun
        mass_ratio = float(np.clip(np.exp(-dv_opt / (self.params.g0 * self.params.I_sp)), 1e-10, 0.999))
        return {'T_d': T_d_opt, 'T_t': T_t_opt, 'delta_v': dv_opt,
                'T_a': T_d_opt + T_t_opt, 'mass_ratio': mass_ratio}


# Cell 18 — build_milp
def build_milp(params: Parameters, sets: Dict, mass_ratios: Dict,
               node_to_name: Dict, node_to_body: Dict) -> Tuple[gp.Model, Dict]:
    model = gp.Model("VRTPP-PR")
    model.setParam('OutputFlag', 0)
    model.setParam('MIPGap', 0.03)  # overridden by solve_vrtpp_pr for experiments

    Bs, V, R, M = sets['Bs'], sets['V'], sets['R'], sets['M']
    k_prime = sets['k_prime']
    m_dry, m_max, q_max = params.m_dry, params.m_max, params.q_max
    lambda_w, m_m, p = params.lambda_weight, params.mining_mass, params.profit

    x, u, q, r, y = {}, {}, {}, {}, {}
    for k in Bs:
        for j in V:
            x[k, k, j] = model.addVar(vtype=GRB.BINARY)
    for k in Bs:
        for i in V:
            for j in V:
                if i != j and node_to_body[i].name != node_to_body[j].name:
                    x[k, i, j] = model.addVar(vtype=GRB.BINARY)
    for k in Bs:
        for i in V:
            x[k, i, k_prime[k]] = model.addVar(vtype=GRB.BINARY)
    for i in Bs + V:
        u[i] = model.addVar(lb=0, ub=m_max)
    for i in V:
        q[i] = model.addVar(lb=0, ub=q_max)
    for i in R:
        r[i] = model.addVar(lb=0)
    for k in Bs:
        for i in V:
            y[k, i] = model.addVar(lb=0, ub=q_max)
    model.update()

    profit_term = gp.quicksum(
        p * (gp.quicksum(x[k, i, j] for k in Bs for j in V if i != j) +
             gp.quicksum(x[k, i, k_prime[k]] for k in Bs))
        for i in M)
    fuel_term = (gp.quicksum(u[k] - m_dry * gp.quicksum(x[k, k, j] for j in V) for k in Bs) +
                 gp.quicksum(r[i] for i in R))
    model.setObjective(profit_term - lambda_w * fuel_term, GRB.MAXIMIZE)

    for k in Bs:
        model.addConstr(gp.quicksum(x[k, k, j] for j in V) <= 1)
    for j in R:
        model.addConstr(gp.quicksum(x[k, k, j] for k in Bs) +
                        gp.quicksum(x[k, i, j] for k in Bs for i in V
                                    if i != j and (k, i, j) in x) <= 1)
    for i in M:
        model.addConstr(gp.quicksum(x[k, i, j] for k in Bs for j in V if i != j) +
                        gp.quicksum(x[k, i, k_prime[k]] for k in Bs) <= 1)
    for j in V:
        for k in Bs:
            model.addConstr(x[k, k, j] - x[k, j, k_prime[k]] +
                            gp.quicksum(x[k, i, j] - x[k, j, i] for i in V
                                        if i != j and (k, i, j) in x) == 0)

    for k in Bs:
        for j in V:
            if (k, j) in mass_ratios:
                model.addConstr(u[j] <= mass_ratios[(k, j)] * u[k] + m_max * (1 - x[k, k, j]))
    for i in M:
        for j in V:
            if i != j and (i, j) in mass_ratios:
                m_ij = mass_ratios[(i, j)]
                if np.isfinite(m_ij) and 0 < m_ij <= 1:
                    model.addConstr(u[j] <= m_ij * (u[i] + m_m) + m_max * (1 - gp.quicksum(x[k, i, j] for k in Bs)))
    for i in R:
        for j in V:
            if i != j and (i, j) in mass_ratios:
                m_ij = mass_ratios[(i, j)]
                if np.isfinite(m_ij) and 0 < m_ij <= 1:
                    model.addConstr(u[j] <= m_ij * (u[i] + r[i]) + m_max * (1 - gp.quicksum(x[k, i, j] for k in Bs)))
    for i in M:
        for k in Bs:
            if (i, k_prime[k]) in mass_ratios:
                model.addConstr(m_dry + y[k, i] <= mass_ratios[(i, k_prime[k])] * (u[i] + m_m) +
                                m_max * (1 - x[k, i, k_prime[k]]))
    for i in R:
        for k in Bs:
            if (i, k_prime[k]) in mass_ratios:
                model.addConstr(m_dry + y[k, i] <= mass_ratios[(i, k_prime[k])] * (u[i] + r[i]) +
                                m_max * (1 - x[k, i, k_prime[k]]))

    for j in M:
        model.addConstr(q[j] >= m_m - q_max * (1 - gp.quicksum(x[k, k, j] for k in Bs)))
    for i in V:
        for j in M:
            if i != j:
                model.addConstr(q[j] >= q[i] + m_m - q_max * (1 - gp.quicksum(x[k, i, j] for k in Bs)))
    for i in V:
        for j in R:
            if i != j:
                model.addConstr(q[j] >= q[i] - q_max * (1 - gp.quicksum(x[k, i, j] for k in Bs if (k, i, j) in x)))

    for i in M:
        model.addConstr(u[i] >= m_dry + q[i] - m_m)
        model.addConstr(u[i] + m_m <= m_max)
    for i in R:
        model.addConstr(u[i] >= m_dry + q[i])
        model.addConstr(u[i] + r[i] <= m_max)
    for k in Bs:
        for i in V:
            model.addConstr(y[k, i] <= q[i])
            model.addConstr(y[k, i] <= q_max * x[k, i, k_prime[k]])
            model.addConstr(y[k, i] >= q[i] - q_max * (1 - x[k, i, k_prime[k]]))

    return model, {'x': x, 'u': u, 'q': q, 'r': r, 'y': y}


# Cell 20 — extract_routes
def extract_routes(x_vars: Dict, sets: Dict) -> List[List[int]]:
    routes = []
    for k in sets['Bs']:
        route = [k]
        current = k
        visited = {k}
        for _ in range(len(sets['V']) + 2):
            next_node = None
            for key, var in x_vars.items():
                if len(key) == 3 and key[0] == k and key[1] == current:
                    try:
                        if var.X > 0.5:
                            next_node = key[2]; break
                    except Exception:
                        continue
            if next_node is None: break
            if next_node in visited and next_node not in sets['Be']: break
            visited.add(next_node)
            route.append(next_node)
            if next_node in sets['Be']: break
            current = next_node
        if len(route) > 2:
            routes.append(route)
    return routes


# Cell 21 — initialize_mass_ratios (TA-grid + distance-corrected T_t seeds)
def initialize_mass_ratios(params: Parameters, sets: Dict, node_to_body: Dict) -> Tuple[Dict, Dict, Dict]:
    """Initialize mass ratios using TA-grid with distance-corrected T_t seeds."""
    print("Initializing mass ratios (TA-grid + distance-corrected T_t seeds)...")
    traj_opt = TrajectoryOptimizer(params)
    mass_ratios = {}
    all_source = sets['Bs'] + sets['V']
    all_dest   = sets['V'] + list(set(sets['Be']))
    body_pair_cache, body_pair_times, body_pair_seed = {}, {}, {}
    init_times = {}
    eps = 1e-5
    N_TA    = 16
    T_d_max = 14.0

    for i in all_source:
        for j in all_dest:
            if i == j: continue
            body_i, body_j = node_to_body[i], node_to_body[j]
            if body_i.name == body_j.name: continue
            pair_key = (body_i.name, body_j.name)
            if pair_key in body_pair_cache:
                mass_ratios[(i, j)] = body_pair_cache[pair_key]
                init_times[(i, j)]  = body_pair_times[pair_key]
                continue

            a_hoh   = (body_i.a + body_j.a) / 2.0
            T_t_hoh = np.pi * np.sqrt(a_hoh**3)

            T_d_candidates = []
            for k in range(N_TA):
                nu = k * 2 * np.pi / N_TA
                t_cand = body_i.time_at_true_anomaly_after(nu, 0.0)
                if 0.0 <= t_cand <= T_d_max:
                    T_d_candidates.append(t_cand)
            if not T_d_candidates:
                T_d_candidates = [0.0]

            best_dv, best_td, best_tt = 1e6, 0.0, T_t_hoh
            best_tt_type = 'none'

            for T_d in T_d_candidates:
                r_dep   = np.linalg.norm(body_i.position_at_time(T_d))
                a_ecc   = (r_dep + body_j.a) / 2.0
                T_t_ecc = np.pi * np.sqrt(a_ecc**3)
                T_t_seeds = sorted(set([
                    max(eps, T_t_hoh * 0.5), max(eps, T_t_hoh),
                    max(eps, T_t_ecc),        max(eps, T_t_hoh * 2.0),
                ]))
                for T_t in T_t_seeds:
                    try:
                        dv = traj_opt.compute_delta_v(body_i, body_j, T_d, T_t)
                        if np.isfinite(dv) and dv < best_dv:
                            best_dv, best_td, best_tt = dv, T_d, T_t
                            if abs(T_t - T_t_ecc) < 1e-6 and abs(T_t_ecc - T_t_hoh) > 0.1:
                                best_tt_type = 'ecc'
                            elif abs(T_t - T_t_hoh) < 1e-6:
                                best_tt_type = 'hoh'
                            elif T_t < T_t_hoh - 0.1:
                                best_tt_type = 'fast'
                            else:
                                best_tt_type = 'slow'
                    except Exception:
                        continue

            if best_dv < 50.0:
                def objective(x):
                    T_d_opt, T_t_opt = x
                    if T_t_opt < eps: return 1e6
                    try:    return traj_opt.compute_delta_v(body_i, body_j, T_d_opt, T_t_opt)
                    except: return 1e6
                try:
                    res = minimize(objective, [best_td, best_tt], method='L-BFGS-B',
                                   bounds=[(0.0, None), (eps, None)],
                                   options={'maxiter': 200, 'ftol': 1e-10})
                    if np.isfinite(res.fun) and res.fun < best_dv:
                        best_dv, best_td, best_tt = res.fun, float(res.x[0]), float(res.x[1])
                except Exception:
                    pass

            if np.isfinite(best_dv) and 0 < best_dv < 50.0:
                mass_ratios[(i, j)] = float(np.clip(
                    np.exp(-best_dv / (params.g0 * params.I_sp)), 1e-4, 0.999))
            else:
                mass_ratios[(i, j)] = 0.05

            init_times[(i, j)]        = (best_td, best_tt)
            body_pair_cache[pair_key] = mass_ratios[(i, j)]
            body_pair_times[pair_key] = (best_td, best_tt)
            body_pair_seed[pair_key]  = best_tt_type

    valid_count = sum(1 for mr in mass_ratios.values() if np.isfinite(mr) and 0 < mr <= 1)
    print(f"  Initialized {len(mass_ratios)} transfers ({valid_count} valid)")
    mr_values = [v for v in mass_ratios.values() if v < 0.99]
    if mr_values:
        print(f"  Mass ratio range: [{min(mr_values):.4f}, {max(mr_values):.4f}]")
    return mass_ratios, init_times, body_pair_seed


# Cell 24 — solve_vrtpp_pr (adapted for experiment runner)
def solve_vrtpp_pr(params: Parameters, sets: Dict, node_to_body: Dict,
                   node_to_name: Dict, max_iterations: int = 50,
                   convergence_tol: float = 1e-3, verbose: bool = True,
                   time_limit: float = 100.0, mip_gap: float = 0.03) -> Dict:
    """
    Complete iterative MILP-NLP algorithm.

    verbose=False suppresses per-iteration output (used by experiment runner).
    time_limit and mip_gap override the defaults in build_milp.
    Returns solution dict compatible with both notebook and experiment runner.
    """
    traj_opt = TrajectoryOptimizer(params)
    mass_ratios, init_times, _ = initialize_mass_ratios(params, sets, node_to_body)
    delta_v_matrix, arc_results = {}, {}
    warm_start, prev_routes = None, None
    stable_route_iters = 0
    consecutive_no_routes = 0
    mip_gaps = []
    start_time = time.time()
    routes = []

    for iteration in range(max_iterations):
        if verbose:
            print(f"\n{'='*60}\nITERATION {iteration + 1}\n{'='*60}")

        model, variables = build_milp(params, sets, mass_ratios, node_to_name, node_to_body)
        model.setParam('MIPGap', mip_gap)
        model.setParam('TimeLimit', time_limit)

        if warm_start:
            for key, val in warm_start.items():
                if key in variables['x']:
                    variables['x'][key].Start = val

        model.optimize()
        mip_gaps.append(model.MIPGap)

        if model.Status == GRB.INFEASIBLE or model.SolCount == 0:
            if iteration == 0:
                return None
            break

        if verbose and model.Status == GRB.TIME_LIMIT:
            print(f"[MILP] Time limit, gap={model.MIPGap*100:.1f}%")

        routes = extract_routes(variables['x'], sets)

        if len(routes) == 0:
            consecutive_no_routes += 1
            if consecutive_no_routes >= 2:
                break
            continue
        else:
            consecutive_no_routes = 0

        if verbose:
            for i, route in enumerate(routes):
                print(f"  SC{i+1}: {' -> '.join(node_to_name[n] for n in route)}")

        old_dv_matrix = delta_v_matrix.copy()
        current_arc_set = {(r[k], r[k+1]) for r in routes for k in range(len(r)-1)}

        for spacecraft_route in routes:
            T_arrival = 0.0
            for k in range(len(spacecraft_route) - 1):
                node_i, node_j = spacecraft_route[k], spacecraft_route[k+1]
                arc = (node_i, node_j)
                prev_result = arc_results.get(arc)
                result = traj_opt.optimize_segment(
                    node_to_body[node_i], node_to_body[node_j], T_arrival,
                    T_t_prev=prev_result['T_t'] if prev_result else None,
                    T_d_prev=prev_result['T_d'] if prev_result else None)
                arc_results[arc] = result
                delta_v_matrix[arc] = result['delta_v']
                mass_ratios[arc]    = result['mass_ratio']
                T_arrival           = result['T_a']
                if verbose:
                    print(f"  {node_to_name[node_i]} -> {node_to_name[node_j]}: "
                          f"dv={result['delta_v']:.2f} km/s")

        if iteration > 0:
            def route_body_sig(rts):
                return frozenset(tuple(node_to_body[n].name for n in r) for r in rts)

            route_changed = prev_routes is None or route_body_sig(routes) != route_body_sig(prev_routes)
            if route_changed:
                stable_route_iters = 0
            else:
                stable_route_iters += 1
                if old_dv_matrix:
                    diff_sq, max_dv_old = 0.0, 0.0
                    for arc in current_arc_set:
                        dv_new = delta_v_matrix.get(arc, 0.0)
                        dv_old = old_dv_matrix.get(arc, 0.0)
                        diff_sq   += (dv_new - dv_old) ** 2
                        max_dv_old = max(max_dv_old, dv_old)
                    change = np.sqrt(diff_sq) / max_dv_old if max_dv_old > 0 else 0.0
                    if verbose:
                        print(f"[CONV] dv change={change:.6f}, stable={stable_route_iters}")
                    if change < convergence_tol or (stable_route_iters >= 5 and change < 0.05):
                        elapsed = time.time() - start_time
                        gap_final = mip_gaps[-1] if mip_gaps else 0.0
                        gap_mean  = statistics.mean(mip_gaps) if mip_gaps else 0.0
                        return {'status': 'converged', 'iterations': iteration + 1,
                                'elapsed': elapsed, 'routes': routes,
                                'mip_gap_final': gap_final, 'mip_gap_mean': gap_mean}

        prev_routes = [r[:] for r in routes]
        warm_start = {}
        for k, v in variables['x'].items():
            try:
                if v.X > 0.5: warm_start[k] = v.X
            except Exception:
                continue

    elapsed    = time.time() - start_time
    gap_final  = mip_gaps[-1] if mip_gaps else 0.0
    gap_mean   = statistics.mean(mip_gaps) if mip_gaps else 0.0
    return {'status': 'max_iterations', 'iterations': max_iterations,
            'elapsed': elapsed, 'routes': routes,
            'mip_gap_final': gap_final, 'mip_gap_mean': gap_mean}


# ── Experiment-specific helpers ───────────────────────────────────────────────
def generate_random_asteroids(n_r, n_m, seed=None):
    rng = random.Random(seed)
    def rb(name):
        return OrbitalBody(name, a=rng.uniform(1, 3), e=rng.uniform(0, 0.3),
                           i=rng.uniform(0, 5), Omega=rng.uniform(0, 360),
                           omega=rng.uniform(0, 360), M0=rng.uniform(0, 360))
    return ([rb(f"R{k+1}") for k in range(n_r)],
            [rb(f"M{k+1}") for k in range(n_m)])


# ── CSV / README helpers ──────────────────────────────────────────────────────
HEADER = ("model,n_r,n_m,iterations_min,iterations_max,iterations_mean,"
          "time_min_sec,time_max_sec,time_mean_sec,"
          "mining_asteroids_min,mining_asteroids_max,mining_asteroids_mean,"
          "trivial_problems,non_converged_problems,"
          "mip_gap_final_min,mip_gap_final_max,mip_gap_final_mean,notes")


def load_csv():
    with open(RESULTS_CSV) as f:
        return list(csv.DictReader(f))


def save_csv(rows):
    with open(RESULTS_CSV, 'w', newline='') as f:
        f.write(HEADER + '\n')
        for r in rows:
            f.write(','.join([
                r['model'], r['n_r'], r['n_m'],
                r['iterations_min'], r['iterations_max'], r['iterations_mean'],
                r['time_min_sec'], r['time_max_sec'], r['time_mean_sec'],
                r['mining_asteroids_min'], r['mining_asteroids_max'], r['mining_asteroids_mean'],
                r['trivial_problems'], r['non_converged_problems'],
                r.get('mip_gap_final_min', ''), r.get('mip_gap_final_max', ''),
                r.get('mip_gap_final_mean', ''), r.get('notes', '')
            ]) + '\n')


def update_csv_row(n_r, n_m, s):
    rows = load_csv()
    for r in rows:
        if r['model'] == 'our_model' and int(r['n_r']) == n_r and int(r['n_m']) == n_m:
            r['iterations_min']        = str(s['iter_min'])
            r['iterations_max']        = str(s['iter_max'])
            r['iterations_mean']       = str(round(s['iter_mean'], 1))
            r['time_min_sec']          = str(round(s['time_min'], 2))
            r['time_max_sec']          = str(round(s['time_max'], 2))
            r['time_mean_sec']         = str(round(s['time_mean'], 2))
            r['mining_asteroids_min']  = str(s['mine_min'])
            r['mining_asteroids_max']  = str(s['mine_max'])
            r['mining_asteroids_mean'] = str(round(s['mine_mean'], 1))
            r['trivial_problems']      = str(s['trivials'])
            r['non_converged_problems'] = str(s['non_convs'])
            r['mip_gap_final_min']     = str(round(s['gap_min'], 6))
            r['mip_gap_final_max']     = str(round(s['gap_max'], 6))
            r['mip_gap_final_mean']    = str(round(s['gap_mean'], 6))
            r['notes'] = (f"{N_INSTANCES} random instances seed {BASE_SEED}-"
                          f"{BASE_SEED + N_INSTANCES - 1}; "
                          f"MIPGap={MILP_MIP_GAP} TimeLimit={int(MILP_TIME_LIMIT)}s")
            break
    save_csv(rows)
    print(f"  ✓ results.csv updated for n_r={n_r}, n_m={n_m}", flush=True)


def update_readme():
    rows = load_csv()
    our  = [r for r in rows if r['model'] == 'our_model']
    c    = lambda v: v if v else ' '
    hdr  = ("| n_r | n_m | Iter min | Iter max | Iter mean | "
            "Time min | Time max | Time mean | Mine min | Mine max | Mine mean | "
            "Trivial | Non-conv | Notes |\n"
            "|-----|-----|----------|----------|-----------|"
            "----------|----------|-----------|----------|----------|-----------|"
            "---------|----------|-------|")
    body = '\n'.join(
        f"| {r['n_r']} | {r['n_m']} | {c(r['iterations_min'])} | {c(r['iterations_max'])} |"
        f" {c(r['iterations_mean'])} | {c(r['time_min_sec'])} | {c(r['time_max_sec'])} |"
        f" {c(r['time_mean_sec'])} | {c(r['mining_asteroids_min'])} | {c(r['mining_asteroids_max'])} |"
        f" {c(r['mining_asteroids_mean'])} | {c(r['trivial_problems'])} | {c(r['non_converged_problems'])} |"
        f" {c(r.get('notes', ''))} |"
        for r in our)
    new_section = ("## Our Model Results\n\n"
                   "*(Updated automatically by run_experiments.py)*\n\n" + hdr + '\n' + body + '\n')
    with open(README_PATH) as f:
        content = f.read()
    ms  = "## Our Model Results"
    idx = content.find(ms)
    nxt = content.find("\n## ", idx + len(ms))
    if idx != -1 and nxt != -1:
        content = content[:idx] + new_section + content[nxt:]
    elif idx != -1:
        content = content[:idx] + new_section
    else:
        content += '\n' + new_section
    with open(README_PATH, 'w') as f:
        f.write(content)
    print("  ✓ README.md updated", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="VRTPP-PR scalability experiments")
    parser.add_argument('--config', nargs=2, type=int, metavar=('N_R', 'N_M'),
                        help='Run only this single config (e.g. --config 1 4)')
    args = parser.parse_args()

    print(f"\n{'='*70}\nVRTPP-PR Scalability Experiments (TA-grid init, Gurobi)\n{'='*70}\n",
          flush=True)

    rows = load_csv()
    done = {(int(r['n_r']), int(r['n_m'])) for r in rows
            if r['model'] == 'our_model' and r['iterations_min']}

    if args.config:
        configs_to_run = [tuple(args.config)]
        print(f"Single config mode: n_r={args.config[0]}, n_m={args.config[1]}", flush=True)
        if tuple(args.config) in done:
            print("Config already completed. Re-running.", flush=True)
    else:
        configs_to_run = [(nr, nm) for nr, nm in ALL_CONFIGS if (nr, nm) not in done]
        print(f"Already done: {sorted(done)}")
        print(f"To run:       {configs_to_run}\n", flush=True)

    for N_R, N_M in configs_to_run:
        print(f"\n{'#'*70}\nCONFIG: n_r={N_R}, n_m={N_M}\n{'#'*70}\n", flush=True)
        inst = []
        for idx in range(N_INSTANCES):
            seed = BASE_SEED + idx
            print(f"  Instance {idx+1}/{N_INSTANCES} (seed={seed})...", end=' ', flush=True)
            ref, mine = generate_random_asteroids(N_R, N_M, seed=seed)
            p   = Parameters()
            s   = build_index_sets(p, N_R, N_M)
            n2b, n2n = build_node_mapping(s, ref, mine)
            sol = solve_vrtpp_pr(p, s, n2b, n2n, verbose=False,
                                 time_limit=MILP_TIME_LIMIT, mip_gap=MILP_MIP_GAP)
            if sol is None:
                inst.append({'iters': 50, 'time': 0., 'mine': 0, 'nc': 1, 'gap': 0.})
                print("failed", flush=True)
            else:
                mc = sum(1 for sr in sol['routes'] for n in sr if n in s['M'])
                nc = 1 if sol['status'] == 'max_iterations' else 0
                inst.append({'iters': sol['iterations'], 'time': sol['elapsed'],
                             'mine': mc, 'nc': nc, 'gap': sol.get('mip_gap_final', 0.)})
                print(f"{sol['status']}, {sol['iterations']} iters, "
                      f"{sol['elapsed']:.1f}s, {mc} mine, gap={sol.get('mip_gap_final', 0.):.4f}",
                      flush=True)

        iters  = [r['iters'] for r in inst]
        times  = [r['time']  for r in inst]
        mines  = [r['mine']  for r in inst]
        gaps   = [r['gap']   for r in inst]
        stats  = {
            'iter_min': min(iters), 'iter_max': max(iters), 'iter_mean': statistics.mean(iters),
            'time_min': min(times), 'time_max': max(times), 'time_mean': statistics.mean(times),
            'mine_min': min(mines), 'mine_max': max(mines), 'mine_mean': statistics.mean(mines),
            'trivials': sum(1 for r in inst if r['mine'] == 0),
            'non_convs': sum(r['nc'] for r in inst),
            'gap_min': min(gaps), 'gap_max': max(gaps), 'gap_mean': statistics.mean(gaps),
        }
        print(f"\n  iter {stats['iter_min']}-{stats['iter_max']} "
              f"(mean {stats['iter_mean']:.1f}) | "
              f"time {stats['time_min']:.1f}-{stats['time_max']:.1f}s "
              f"(mean {stats['time_mean']:.1f}s) | "
              f"mine {stats['mine_min']}-{stats['mine_max']} "
              f"(mean {stats['mine_mean']:.1f})")
        update_csv_row(N_R, N_M, stats)

    if not args.config:
        print("\nAll experiments done. Updating README...", flush=True)
        update_readme()
    print("Done!", flush=True)


if __name__ == '__main__':
    main()
