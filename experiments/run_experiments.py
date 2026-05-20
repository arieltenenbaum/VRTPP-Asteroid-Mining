"""
run_experiments.py – Run all missing VRTPP-PR scalability experiments (Gurobi).

Run from the repo root:
    python3 experiments/run_experiments.py

Results are written to experiments/results.csv incrementally (progress is
saved after every configuration), and experiments/README.md is updated at
the end.
"""

import os, sys, time, csv, statistics, random, warnings
import numpy as np
from scipy.optimize import minimize, Bounds as ScipyBounds
from typing import Dict, List, Tuple
from dataclasses import dataclass
import gurobipy as gp
from gurobipy import GRB

warnings.filterwarnings("ignore")

# ── File paths ───────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(SCRIPT_DIR, "results.csv")
README_PATH = os.path.join(SCRIPT_DIR, "README.md")

# ── Configurations & settings ────────────────────────────────────────────────
ALL_CONFIGS = [
    (1, 4), (1, 6), (1, 8),
    (2, 4), (2, 6), (2, 8),
    (3, 4), (3, 6), (3, 8),
]
N_INSTANCES = 5
BASE_SEED   = 42

# ── Orbital mechanics ─────────────────────────────────────────────────────────
class OrbitalBody:
    def __init__(self, name, a, e, i, Omega, omega, M0, epoch=0.0):
        self.name  = name;  self.a = a;  self.e = e;  self.epoch = epoch
        self.i     = np.deg2rad(i);    self.Omega = np.deg2rad(Omega)
        self.omega = np.deg2rad(omega); self.M0   = np.deg2rad(M0)

    def position_at_time(self, t, mu=1.0):
        n = np.sqrt(mu / self.a**3);  M = self.M0 + n*(t - self.epoch)
        E = self._kepler(M, self.e)
        nu = 2*np.arctan2(np.sqrt(1+self.e)*np.sin(E/2), np.sqrt(1-self.e)*np.cos(E/2))
        r = self.a*(1 - self.e*np.cos(E))
        return self._R() @ np.array([r*np.cos(nu), r*np.sin(nu), 0.0])

    def velocity_at_time(self, t, mu=1.0):
        n = np.sqrt(mu / self.a**3);  M = self.M0 + n*(t - self.epoch)
        E = self._kepler(M, self.e)
        nu = 2*np.arctan2(np.sqrt(1+self.e)*np.sin(E/2), np.sqrt(1-self.e)*np.cos(E/2))
        h = np.sqrt(mu*self.a*(1 - self.e**2))
        return self._R() @ np.array([-(mu/h)*np.sin(nu), (mu/h)*(self.e+np.cos(nu)), 0.0])

    def _kepler(self, M, e, tol=1e-10):
        E = M if e < 0.8 else np.pi
        for _ in range(50):
            dE = (E - e*np.sin(E) - M) / (1 - e*np.cos(E))
            E -= dE
            if abs(dE) < tol: break
        return E

    def _R(self):
        cO,sO = np.cos(self.Omega),np.sin(self.Omega)
        ci,si = np.cos(self.i),    np.sin(self.i)
        cw,sw = np.cos(self.omega),np.sin(self.omega)
        return np.array([
            [cO*cw-sO*ci*sw, -cO*sw-sO*ci*cw,  sO*si],
            [sO*cw+cO*ci*sw, -sO*sw+cO*ci*cw, -cO*si],
            [si*sw,           si*cw,             ci  ],
        ])


earth = OrbitalBody("Earth", a=1.0009, e=0.0173, i=0.0032,
                    Omega=171.7283, omega=289.5838, M0=318.5855)


class LambertSolver:
    def __init__(self, mu=1.0): self.mu = mu

    def solve(self, r1v, r2v, tof, prograde=True):
        r1,r2 = np.linalg.norm(r1v), np.linalg.norm(r2v)
        cdnu  = np.clip(np.dot(r1v,r2v)/(r1*r2), -1,1)
        cross = np.cross(r1v, r2v)
        if prograde: dnu = np.arccos(cdnu) if cross[2]>=0 else 2*np.pi-np.arccos(cdnu)
        else:        dnu = np.arccos(cdnu) if cross[2]< 0 else 2*np.pi-np.arccos(cdnu)
        A = np.sin(dnu)*np.sqrt(r1*r2/(1-cdnu))
        if abs(A)<1e-14: raise ValueError("Degenerate Lambert")

        def C2(p):
            if p>1e-6:  return (1-np.cos(np.sqrt(p)))/p
            if p<-1e-6: return (np.cosh(np.sqrt(-p))-1)/(-p)
            return 0.5
        def C3(p):
            if p>1e-6:  s=np.sqrt(p);  return (s-np.sin(s))/(p*s)
            if p<-1e-6: s=np.sqrt(-p); return (np.sinh(s)-s)/((-p)*s)
            return 1/6

        psi_n,pu,pl_ = 0.0, 4*np.pi**2, -4*np.pi**2
        for _ in range(100):
            c2,c3 = C2(psi_n),C3(psi_n)
            y_n   = r1+r2+A*(psi_n*c3-1)/np.sqrt(c2)
            if y_n < 0:
                for _ in range(2000):
                    psi_n+=0.1; c2,c3=C2(psi_n),C3(psi_n)
                    y_n=r1+r2+A*(psi_n*c3-1)/np.sqrt(c2)
                    if y_n>=0: break
                else: raise ValueError("Lambert: no valid y_n")
            chi   = np.sqrt(y_n/c2)
            tof_n = (chi**3*c3+A*np.sqrt(y_n))/np.sqrt(self.mu)
            if abs(tof_n-tof)<1e-8*abs(tof): break
            if tof_n<=tof: pl_=psi_n
            else:          pu =psi_n
            dt = ((chi**3*(C3(psi_n)-3*c3*C2(psi_n)/(2*c2))/(2*c2)+
                   (A/8)*(3*c3*np.sqrt(y_n)/c2+A/chi))/np.sqrt(self.mu))
            psi_new = psi_n+(tof-tof_n)/dt if abs(dt)>1e-14 else (pu+pl_)/2
            psi_n   = psi_new if pl_<=psi_new<=pu else (pu+pl_)/2
        f,gd = 1-y_n/r1, 1-y_n/r2
        g    = A*np.sqrt(y_n/self.mu)
        if abs(g)<1e-14: raise ValueError("Lambert: g near zero")
        return (r2v-f*r1v)/g, (gd*r2v-r1v)/g


# ── Parameters ────────────────────────────────────────────────────────────────
@dataclass
class Parameters:
    mu_sun:float=1.0; mu_earth:float=3.986e5; g0:float=9.81e-3
    m_dry:float=300.0; m_max:float=20000.0; q_max:float=30.0; I_sp:float=457.0
    n_bv:int=3; n_rv:int=3; T_service:float=2.0/58.132; lambda_weight:float=5e-5
    profit:float=10.0; mining_mass:float=10.0; r0_park:float=7000.0
    AU_to_km:float=1.496e8; TU_to_sec:float=58.132*86400


# ── Index sets ────────────────────────────────────────────────────────────────
def build_index_sets(params, n_refuel, n_mine):
    nb,nrv = params.n_bv, params.n_rv
    Bs = list(range(0, nb+1));              Be = list(range(nb+1, 2*nb+2))
    R0 = list(range(2*nb+2, 2*nb+n_refuel+2))
    Rv = list(range(2*nb+n_refuel+2, 2*nb+n_refuel*nrv+2))
    R  = R0+Rv
    M  = list(range(2*nb+n_refuel*nrv+2, 2*nb+n_refuel*nrv+n_mine+2))
    V  = R+M;  N = Bs+Be+V
    return {'B0':[0],'Bv':list(range(1,nb+1)),'Bs':Bs,'Be':Be,
            'R0':R0,'Rv':Rv,'R':R,'M':M,'V':V,'N':N,
            'k_prime':{k:k+nb+1 for k in Bs}}


def build_node_mapping(sets, refueling_bodies, mining_bodies):
    n2b,n2n = {},{}
    for nd in sets['Bs']+sets['Be']: n2b[nd]=earth; n2n[nd]="Earth"
    for i,nd in enumerate(sets['R']):
        b=refueling_bodies[i%len(refueling_bodies)]; n2b[nd]=b; n2n[nd]=b.name
    for i,nd in enumerate(sets['M']):
        b=mining_bodies[i]; n2b[nd]=b; n2n[nd]=b.name
    return n2b, n2n


def generate_random_asteroids(n_r, n_m, seed=None):
    rng = random.Random(seed)
    def rb(name):
        return OrbitalBody(name, a=rng.uniform(1,3), e=rng.uniform(0,0.3),
                           i=rng.uniform(0,5), Omega=rng.uniform(0,360),
                           omega=rng.uniform(0,360), M0=rng.uniform(0,360))
    return [rb("R"+str(k+1)) for k in range(n_r)], \
           [rb("M"+str(k+1)) for k in range(n_m)]


# ── Trajectory optimizer ──────────────────────────────────────────────────────
class TrajectoryOptimizer:
    def __init__(self, params):
        self.p = params;  self.lam = LambertSolver(mu=params.mu_sun)

    def dv(self, bi, bj, Td, Tt):
        r1=bi.position_at_time(Td,   self.p.mu_sun)
        r2=bj.position_at_time(Td+Tt,self.p.mu_sun)
        v1o=bi.velocity_at_time(Td,   self.p.mu_sun)
        v2o=bj.velocity_at_time(Td+Tt,self.p.mu_sun)
        try: v1t,v2t = self.lam.solve(r1,r2,Tt,prograde=True)
        except: return 100.0
        cv = self.p.AU_to_km/self.p.TU_to_sec
        d1 = self._edv((v1t-v1o)*cv) if bi.name=="Earth" else np.linalg.norm(v1t-v1o)*cv
        d2 = self._edv((v2o-v2t)*cv) if bj.name=="Earth" else np.linalg.norm(v2o-v2t)*cv
        return d1+d2

    def _edv(self, v_inf):
        v=np.linalg.norm(v_inf); vp=np.sqrt(self.p.mu_earth/self.p.r0_park)
        return abs(np.sqrt(v**2+2*self.p.mu_earth/self.p.r0_park)-vp)

    def optimize_segment(self, bi, bj, T_arr, T_t_prev=None, T_d_prev=None):
        eps=1e-5
        svc = self.p.T_service if bi.name!="Earth" else 0.0
        Td_min, Td_max = T_arr+svc, T_arr+svc+5.0
        if T_t_prev is None:
            best_dv,best_tt=1e9,1.0
            for tt in np.arange(1.0,14.0,2.0):
                try:
                    d=self.dv(bi,bj,Td_min,tt)
                    if np.isfinite(d) and d<best_dv: best_dv,best_tt=d,tt
                except: pass
            Tt0 = best_tt
        else: Tt0=T_t_prev
        Td0 = float(np.clip(T_d_prev if T_d_prev else Td_min, Td_min, Td_max))
        def obj(x): v=self.dv(bi,bj,x[0],x[1]); return v if np.isfinite(v) else 1e6
        try:
            res=minimize(obj,x0=[Td0,max(Tt0,eps)],method='trust-constr',
                         bounds=ScipyBounds([Td_min,eps],[Td_max,30.0]),
                         options={'maxiter':500,'verbose':0,'gtol':1e-8,'xtol':1e-8})
            ok = res is not None and np.isfinite(res.fun) and res.fun<100.0
        except: ok,res=False,None
        if not ok:
            return {'T_d':Td0,'T_t':max(Tt0,eps),'delta_v':100.0,
                    'T_a':Td0+max(Tt0,eps),'mass_ratio':1e-10}
        Td,Tt = res.x;  dv=res.fun
        mr=float(np.clip(np.exp(-dv/(self.p.g0*self.p.I_sp)),1e-10,0.999))
        return {'T_d':Td,'T_t':Tt,'delta_v':dv,'T_a':Td+Tt,'mass_ratio':mr}


# ── Mass-ratio initialization ─────────────────────────────────────────────────
def init_mass_ratios(params, sets, n2b):
    to = TrajectoryOptimizer(params)
    mr, it = {}, {}
    cache_mr, cache_t = {}, {}
    eps=1e-5
    Tds=np.arange(0,14,1.); Tts=np.arange(1,14,2.)
    src=sets['Bs']+sets['V'];  dst=sets['V']+list(set(sets['Be']))
    for i in src:
        for j in dst:
            if i==j: continue
            bi,bj=n2b[i],n2b[j]
            if bi.name==bj.name: continue
            pk=(bi.name,bj.name)
            if pk in cache_mr:
                mr[(i,j)]=cache_mr[pk]; it[(i,j)]=cache_t[pk]; continue
            best,btd,btt=1e6,0.,1.
            for Td in Tds:
                for Tt in Tts:
                    try:
                        d=to.dv(bi,bj,Td,Tt)
                        if np.isfinite(d) and d<best: best,btd,btt=d,Td,Tt
                    except: pass
            if best<50.:
                def f(x):
                    if x[1]<eps: return 1e6
                    try: return to.dv(bi,bj,x[0],x[1])
                    except: return 1e6
                try:
                    r=minimize(f,[btd,btt],method='L-BFGS-B',
                               bounds=[(0.,None),(eps,None)],
                               options={'maxiter':200,'ftol':1e-10})
                    if np.isfinite(r.fun) and r.fun<best:
                        best,btd,btt=r.fun,float(r.x[0]),float(r.x[1])
                except: pass
            if np.isfinite(best) and 0<best<50.:
                v=float(np.clip(np.exp(-best/(params.g0*params.I_sp)),1e-4,0.999))
            else: v=0.05
            mr[(i,j)]=v; it[(i,j)]=(btd,btt)
            cache_mr[pk]=v; cache_t[pk]=(btd,btt)
    return mr, it


# ── MILP (Gurobi) ─────────────────────────────────────────────────────────────
def build_milp(params, sets, mr, n2n, n2b):
    m=gp.Model("VRTPP-PR"); m.setParam('OutputFlag',0); m.setParam('MIPGap',0.0)
    Bs,V,R,M,kp=sets['Bs'],sets['V'],sets['R'],sets['M'],sets['k_prime']
    md,mx,qx=params.m_dry,params.m_max,params.q_max
    lw,mm,p=params.lambda_weight,params.mining_mass,params.profit
    x,u,q,r,y={},{},{},{},{}
    for k in Bs:
        for j in V:             x[k,k,j]=m.addVar(vtype=GRB.BINARY)
    for k in Bs:
        for i in V:
            for j in V:
                if i!=j and n2b[i].name!=n2b[j].name: x[k,i,j]=m.addVar(vtype=GRB.BINARY)
    for k in Bs:
        for i in V:             x[k,i,kp[k]]=m.addVar(vtype=GRB.BINARY)
    for i in Bs+V:              u[i]=m.addVar(lb=0,ub=mx)
    for i in V:                 q[i]=m.addVar(lb=0,ub=qx)
    for i in R:                 r[i]=m.addVar(lb=0)
    for k in Bs:
        for i in V:             y[k,i]=m.addVar(lb=0,ub=qx)
    m.update()
    pt=gp.quicksum(
        p*(gp.quicksum(x[k,i,j] for k in Bs for j in V if i!=j and (k,i,j) in x)+
           gp.quicksum(x[k,i,kp[k]] for k in Bs))
        for i in M)
    ft=(gp.quicksum(u[k]-md*gp.quicksum(x[k,k,j] for j in V) for k in Bs)+
        gp.quicksum(r[i] for i in R))
    m.setObjective(pt-lw*ft, GRB.MAXIMIZE)
    for k in Bs: m.addConstr(gp.quicksum(x[k,k,j] for j in V)<=1)
    for j in R:
        m.addConstr(gp.quicksum(x[k,k,j] for k in Bs)+
                    gp.quicksum(x[k,i,j] for k in Bs for i in V if i!=j and (k,i,j) in x)<=1)
    for i in M:
        m.addConstr(gp.quicksum(x[k,i,j] for k in Bs for j in V if i!=j and (k,i,j) in x)+
                    gp.quicksum(x[k,i,kp[k]] for k in Bs)<=1)
    for j in V:
        for k in Bs:
            m.addConstr(x[k,k,j]-x[k,j,kp[k]]+
                        gp.quicksum(x[k,i,j]-x[k,j,i] for i in V if i!=j and (k,i,j) in x and (k,j,i) in x)+
                        gp.quicksum(x[k,i,j] for i in V if i!=j and (k,i,j) in x and (k,j,i) not in x)-
                        gp.quicksum(x[k,j,i] for i in V if i!=j and (k,j,i) in x and (k,i,j) not in x)==0)
    for k in Bs:
        for j in V:
            if (k,j) in mr: m.addConstr(u[j]<=mr[(k,j)]*u[k]+mx*(1-x[k,k,j]))
    for i in M:
        for j in V:
            if i!=j and (i,j) in mr and np.isfinite(mr[(i,j)]) and 0<mr[(i,j)]<=1:
                m.addConstr(u[j]<=mr[(i,j)]*(u[i]+mm)+mx*(1-gp.quicksum(x[k,i,j] for k in Bs if (k,i,j) in x)))
    for i in R:
        for j in V:
            if i!=j and (i,j) in mr and np.isfinite(mr[(i,j)]) and 0<mr[(i,j)]<=1:
                m.addConstr(u[j]<=mr[(i,j)]*(u[i]+r[i])+mx*(1-gp.quicksum(x[k,i,j] for k in Bs if (k,i,j) in x)))
    for i in M:
        for k in Bs:
            if (i,kp[k]) in mr:
                m.addConstr(md+y[k,i]<=mr[(i,kp[k])]*(u[i]+mm)+mx*(1-x[k,i,kp[k]]))
    for i in R:
        for k in Bs:
            if (i,kp[k]) in mr:
                m.addConstr(md+y[k,i]<=mr[(i,kp[k])]*(u[i]+r[i])+mx*(1-x[k,i,kp[k]]))
    for j in M:
        m.addConstr(q[j]>=mm-qx*(1-gp.quicksum(x[k,k,j] for k in Bs)))
    for i in V:
        for j in M:
            if i!=j:
                m.addConstr(q[j]>=q[i]+mm-qx*(1-gp.quicksum(x[k,i,j] for k in Bs if (k,i,j) in x)))
    for i in V:
        for j in R:
            if i!=j:
                m.addConstr(q[j]>=q[i]-qx*(1-gp.quicksum(x[k,i,j] for k in Bs if (k,i,j) in x)))
    for i in M:
        m.addConstr(u[i]>=md+q[i]-mm); m.addConstr(u[i]+mm<=mx)
    for i in R:
        m.addConstr(u[i]>=md+q[i]);    m.addConstr(u[i]+r[i]<=mx)
    for k in Bs:
        for i in V:
            m.addConstr(y[k,i]<=q[i])
            m.addConstr(y[k,i]<=qx*x[k,i,kp[k]])
            m.addConstr(y[k,i]>=q[i]-qx*(1-x[k,i,kp[k]]))
    return m, {'x':x,'u':u,'q':q,'r':r,'y':y}


# ── Route extraction ──────────────────────────────────────────────────────────
def extract_routes(xv, sets):
    routes=[]
    for k in sets['Bs']:
        route=[k]; cur=k; vis={k}
        for _ in range(len(sets['V'])+2):
            nxt=None
            for key,var in xv.items():
                if len(key)==3 and key[0]==k and key[1]==cur:
                    try:
                        if var.X>0.5: nxt=key[2]; break
                    except: pass
            if nxt is None: break
            if nxt in vis and nxt not in sets['Be']: break
            vis.add(nxt); route.append(nxt)
            if nxt in sets['Be']: break
            cur=nxt
        if len(route)>2: routes.append(route)
    return routes


# ── Solver ────────────────────────────────────────────────────────────────────
def solve(params, sets, n2b, n2n, max_iter=50, tol=1e-3):
    to=TrajectoryOptimizer(params)
    mr,_=init_mass_ratios(params,sets,n2b)
    dv_mat,arc_res={},{}
    ws,prev_routes=None,None
    stable,no_routes=0,0
    t0=time.time()
    routes=[]
    mip_gaps=[]
    for it in range(max_iter):
        model,variables=build_milp(params,sets,mr,n2n,n2b)
        if ws:
            for k,v in ws.items():
                if k in variables['x']: variables['x'][k].Start=v
        model.setParam('TimeLimit',30.0)
        model.optimize()
        mip_gaps.append(model.MIPGap)
        if model.Status==GRB.INFEASIBLE or model.SolCount==0:
            if it==0: return None
            break
        routes=extract_routes(variables['x'],sets)
        if not routes:
            no_routes+=1
            if no_routes>=2: break
            continue
        else: no_routes=0
        old_dv=dv_mat.copy()
        arc_set=set()
        for sr in routes:
            for k in range(len(sr)-1): arc_set.add((sr[k],sr[k+1]))
        for sr in routes:
            Ta=0.0
            for k in range(len(sr)-1):
                ni,nj=sr[k],sr[k+1]; arc=(ni,nj)
                pr=arc_res.get(arc)
                res=to.optimize_segment(n2b[ni],n2b[nj],Ta,
                    T_t_prev=pr['T_t'] if pr else None,
                    T_d_prev=pr['T_d'] if pr else None)
                arc_res[arc]=res; dv_mat[arc]=res['delta_v']
                mr[arc]=res['mass_ratio']; Ta=res['T_a']
        if it>0:
            def sig(rts): return frozenset(tuple(n2b[n].name for n in r) for r in rts)
            changed = prev_routes is None or sig(routes)!=sig(prev_routes)
            if changed: stable=0
            else:
                stable+=1
                if old_dv:
                    ssq,mx2=0.,0.
                    for a in arc_set:
                        dn,do=dv_mat.get(a,0.),old_dv.get(a,0.)
                        ssq+=(dn-do)**2; mx2=max(mx2,do)
                    chg=np.sqrt(ssq)/mx2 if mx2>0 else 0.
                    if chg<tol or (stable>=5 and chg<0.05):
                        gap_final=mip_gaps[-1] if mip_gaps else 0.
                        gap_mean=statistics.mean(mip_gaps) if mip_gaps else 0.
                        return {'status':'converged','iterations':it+1,
                                'elapsed':time.time()-t0,'routes':routes,
                                'mip_gap_final':gap_final,'mip_gap_mean':gap_mean}
        prev_routes=[r[:] for r in routes]
        ws={}
        for k,v in variables['x'].items():
            try:
                if v.X>0.5: ws[k]=v.X
            except: pass
    gap_final=mip_gaps[-1] if mip_gaps else 0.
    gap_mean=statistics.mean(mip_gaps) if mip_gaps else 0.
    return {'status':'max_iterations','iterations':max_iter,
            'elapsed':time.time()-t0,'routes':routes,
            'mip_gap_final':gap_final,'mip_gap_mean':gap_mean}


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
    with open(RESULTS_CSV,'w',newline='') as f:
        f.write(HEADER+'\n')
        for r in rows:
            f.write(','.join([
                r['model'],r['n_r'],r['n_m'],
                r['iterations_min'],r['iterations_max'],r['iterations_mean'],
                r['time_min_sec'],r['time_max_sec'],r['time_mean_sec'],
                r['mining_asteroids_min'],r['mining_asteroids_max'],r['mining_asteroids_mean'],
                r['trivial_problems'],r['non_converged_problems'],
                r.get('mip_gap_final_min',''),r.get('mip_gap_final_max',''),r.get('mip_gap_final_mean',''),
                r.get('notes','')
            ])+'\n')

def update_csv_row(n_r, n_m, s):
    rows=load_csv()
    for r in rows:
        if r['model']=='our_model' and int(r['n_r'])==n_r and int(r['n_m'])==n_m:
            r['iterations_min']=str(s['iter_min']); r['iterations_max']=str(s['iter_max'])
            r['iterations_mean']=str(round(s['iter_mean'],1))
            r['time_min_sec']=str(round(s['time_min'],2)); r['time_max_sec']=str(round(s['time_max'],2))
            r['time_mean_sec']=str(round(s['time_mean'],2))
            r['mining_asteroids_min']=str(s['mine_min']); r['mining_asteroids_max']=str(s['mine_max'])
            r['mining_asteroids_mean']=str(round(s['mine_mean'],1))
            r['trivial_problems']=str(s['trivials']); r['non_converged_problems']=str(s['non_convs'])
            r['mip_gap_final_min']=str(round(s['gap_min'],6))
            r['mip_gap_final_max']=str(round(s['gap_max'],6))
            r['mip_gap_final_mean']=str(round(s['gap_mean'],6))
            r['notes']=f'{N_INSTANCES} random instances seed {BASE_SEED}-{BASE_SEED+N_INSTANCES-1}; MIPGap=0.0 TimeLimit=30s'; break
    save_csv(rows)
    print(f"  ✓ results.csv updated for n_r={n_r}, n_m={n_m}", flush=True)

def update_readme():
    rows=load_csv()
    our=[r for r in rows if r['model']=='our_model']
    c=lambda v: v if v else ' '
    hdr=("| n_r | n_m | Iter min | Iter max | Iter mean | Time min | Time max | Time mean |"
         " Mine min | Mine max | Mine mean | Trivial | Non-conv | Notes |\n"
         "|-----|-----|----------|----------|-----------|----------|----------|-----------|"
         "----------|----------|-----------|---------|----------|-------|")
    body='\n'.join(
        f"| {r['n_r']} | {r['n_m']} | {c(r['iterations_min'])} | {c(r['iterations_max'])} |"
        f" {c(r['iterations_mean'])} | {c(r['time_min_sec'])} | {c(r['time_max_sec'])} |"
        f" {c(r['time_mean_sec'])} | {c(r['mining_asteroids_min'])} | {c(r['mining_asteroids_max'])} |"
        f" {c(r['mining_asteroids_mean'])} | {c(r['trivial_problems'])} | {c(r['non_converged_problems'])} |"
        f" {c(r.get('notes',''))} |"
        for r in our)
    new_section=("## Our Model Results\n\n"
                 "*(Updated automatically by run_experiments.py)*\n\n"+hdr+'\n'+body+'\n')
    with open(README_PATH) as f: content=f.read()
    ms="## Our Model Results"
    idx=content.find(ms)
    nxt=content.find("\n## ", idx+len(ms))
    if idx!=-1 and nxt!=-1: content=content[:idx]+new_section+content[nxt:]
    elif idx!=-1:            content=content[:idx]+new_section
    else:                    content+='\n'+new_section
    with open(README_PATH,'w') as f: f.write(content)
    print("  ✓ README.md updated", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*70}\nVRTPP-PR Scalability Experiments (Gurobi)\n{'='*70}\n", flush=True)
    rows=load_csv()
    done={(int(r['n_r']),int(r['n_m'])) for r in rows
          if r['model']=='our_model' and r['iterations_min']}
    todo=[(nr,nm) for nr,nm in ALL_CONFIGS if (nr,nm) not in done]
    print(f"Already done: {sorted(done)}")
    print(f"To run:       {todo}\n", flush=True)

    for N_R,N_M in todo:
        print(f"\n{'#'*70}\nCONFIG: n_r={N_R}, n_m={N_M}\n{'#'*70}\n", flush=True)
        inst=[]
        for idx in range(N_INSTANCES):
            seed=BASE_SEED+idx
            print(f"  Instance {idx+1}/{N_INSTANCES} (seed={seed})...", end=' ', flush=True)
            ref,mine=generate_random_asteroids(N_R,N_M,seed=seed)
            p=Parameters(); s=build_index_sets(p,N_R,N_M)
            n2b,n2n=build_node_mapping(s,ref,mine)
            sol=solve(p,s,n2b,n2n)
            if sol is None:
                inst.append({'iters':50,'time':0.,'mine':0,'nc':1})
                print("failed", flush=True)
            else:
                mc=sum(1 for sr in sol['routes'] for n in sr if n in s['M'])
                nc=1 if sol['status']=='max_iterations' else 0
                inst.append({'iters':sol['iterations'],'time':sol['elapsed'],'mine':mc,'nc':nc,
                             'gap':sol.get('mip_gap_final',0.)})
                print(f"{sol['status']}, {sol['iterations']} iters, "
                      f"{sol['elapsed']:.1f}s, {mc} mine, gap={sol.get('mip_gap_final',0.):.4f}", flush=True)

        iters=[r['iters'] for r in inst]; times=[r['time'] for r in inst]
        mines=[r['mine']  for r in inst]; gaps=[r['gap'] for r in inst]
        stats={'iter_min':min(iters),'iter_max':max(iters),'iter_mean':statistics.mean(iters),
               'time_min':min(times),'time_max':max(times),'time_mean':statistics.mean(times),
               'mine_min':min(mines),'mine_max':max(mines),'mine_mean':statistics.mean(mines),
               'trivials':sum(1 for r in inst if r['mine']==0),
               'non_convs':sum(r['nc'] for r in inst),
               'gap_min':min(gaps),'gap_max':max(gaps),'gap_mean':statistics.mean(gaps)}
        print(f"\n  iter {stats['iter_min']}-{stats['iter_max']} (mean {stats['iter_mean']:.1f}) | "
              f"time {stats['time_min']:.1f}-{stats['time_max']:.1f}s "
              f"(mean {stats['time_mean']:.1f}s) | "
              f"mine {stats['mine_min']}-{stats['mine_max']} (mean {stats['mine_mean']:.1f})")
        update_csv_row(N_R,N_M,stats)

    print("\nAll experiments done. Updating README...", flush=True)
    update_readme()
    print("Done!", flush=True)


if __name__=='__main__':
    main()
