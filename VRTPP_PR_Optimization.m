function VRTPP_PR_Optimization()
% VRTPP-PR: Optimal Routing and Trajectory Planning for Asteroid Mining
% MATLAB implementation of Choi & Ho, Georgia Institute of Technology, 2026
%
% Requirements: Optimization Toolbox (fmincon), Gurobi MATLAB Interface
% Run: VRTPP_PR_Optimization()

clear; clc;
fprintf('VRTPP-PR Optimization  --  MATLAB Implementation\n\n');

%% ════════════════════════════════════════════════════════════════
%  1. PARAMETERS (Table 2)
%% ════════════════════════════════════════════════════════════════
p.mu_sun    = 1.0;           % AU^3/TU^2
p.mu_earth  = 3.986e5;       % km^3/s^2
p.g0        = 9.81e-3;       % km/s^2
p.m_dry     = 300.0;         % kg
p.m_max     = 20000.0;       % kg
p.q_max     = 30.0;          % kg (max cargo)
p.I_sp      = 457.0;         % s
p.n_bv      = 3;             % virtual spacecraft copies
p.n_rv      = 3;             % virtual refueling copies
p.T_service = 2.0/58.132;    % service time [TU]
p.lambda    = 5e-5;          % fuel penalty weight
p.profit    = 10.0;          % profit per mining asteroid
p.m_mine    = 10.0;          % ore mass per asteroid [kg]
p.r0_park   = 7000.0;        % Earth parking orbit radius [km]
p.AU_to_km  = 1.496e8;
p.TU_to_sec = 58.132 * 86400;

%% ════════════════════════════════════════════════════════════════
%  2. CELESTIAL BODIES (Table 3)
%% ════════════════════════════════════════════════════════════════
earth   = mkbody('Earth',        1.0009,0.0173,0.0032, 171.7283,289.5838,318.5855);
ryugu   = mkbody('162173 Ryugu', 1.1909,0.1911,5.8666, 251.2915,211.6168,270.6594);
bennu   = mkbody('101955 Bennu', 1.1260,0.0204,6.0328, 1.9690,  66.4073, 267.4691);
sg10    = mkbody('2001 SG10',    1.4487,0.4246,4.2568, 184.8938,101.6706,340.8908);
ml      = mkbody('1989 ML',      1.2728,0.1369,4.3791, 104.2721,183.6253,121.5130);
fg3     = mkbody('1996 FG3',     1.0548,0.3501,1.9727, 299.4710,24.0570, 36.6506 );
cc21    = mkbody('2001 CC21',    1.0321,0.2192,4.8086, 75.3575, 179.4026,140.7404);
anteros = mkbody('1943 Anteros', 1.4305,0.2559,8.7077, 246.2935,338.4366,260.3741);

ref_bodies  = {ryugu, bennu};
mine_bodies = {sg10, ml, fg3, cc21, anteros};

%% ════════════════════════════════════════════════════════════════
%  3. INDEX SETS & NODE MAPPING
%% ════════════════════════════════════════════════════════════════
[sets, n2b, n2n] = build_sets(p, ref_bodies, mine_bodies, earth);

fprintf('Node layout:\n');
fprintf('  Bs (start bases) : [%s]\n', num2str(sets.Bs));
fprintf('  Be (end bases)   : [%s]\n', num2str(sets.Be));
fprintf('  R  (refueling)   : [%s]\n', num2str(sets.R));
fprintf('  M  (mining)      : [%s]\n', num2str(sets.M));

%% ════════════════════════════════════════════════════════════════
%  4. VERIFY LAMBERT AGAINST PAPER TABLE 5
%% ════════════════════════════════════════════════════════════════
fprintf('\n--- Trajectory Verification (Paper Table 5) ---\n');
legs = {'Earth->FG3',   earth, fg3,   0.09, 6.26, 9.51;
        'FG3->Bennu',   fg3,   bennu, 8.83, 7.06, 7.32;
        'Bennu->Earth', bennu, earth, 17.59,6.81, 8.17};
for k = 1:size(legs,1)
    bi=legs{k,2}; bj=legs{k,3};
    dv = compute_dv(bi, bj, legs{k,4}, legs{k,5}, p);
    err = abs(dv - legs{k,6}) / legs{k,6} * 100;
    if err < 15, st='OK'; else, st='MISMATCH'; end
    fprintf('  %-16s: computed=%.2f, expected=%.2f km/s, err=%.1f%% [%s]\n', ...
            legs{k,1}, dv, legs{k,6}, err, st);
end
fprintf('--- End Verification ---\n\n');

%% ════════════════════════════════════════════════════════════════
%  5. RUN ITERATIVE MILP-NLP
%% ════════════════════════════════════════════════════════════════
solution = solve_vrtpp(p, sets, n2b, n2n, 50, 1e-3);

%% ════════════════════════════════════════════════════════════════
%  6. DISPLAY RESULTS
%% ════════════════════════════════════════════════════════════════
if ~isempty(solution) && ~isempty(solution.routes)
    display_results(solution, n2n, p);
else
    fprintf('\nNo solution found.\n');
end

end % ── end main ────────────────────────────────────────────────


%% ════════════════════════════════════════════════════════════════════════
%%  LOCAL FUNCTIONS
%% ════════════════════════════════════════════════════════════════════════

%% ── Celestial body constructor ──────────────────────────────────────────
function b = mkbody(name, a, e, i_d, Om_d, om_d, M0_d)
b.name  = name;
b.a     = a;
b.e     = e;
b.i     = deg2rad(i_d);
b.Omega = deg2rad(Om_d);
b.omega = deg2rad(om_d);
b.M0    = deg2rad(M0_d);
b.epoch = 0;
end

%% ── Orbital position ────────────────────────────────────────────────────
function rv = pos_at(b, t, mu)
n  = sqrt(mu / b.a^3);
M  = b.M0 + n*(t - b.epoch);
E  = kepler(M, b.e);
nu = 2*atan2(sqrt(1+b.e)*sin(E/2), sqrt(1-b.e)*cos(E/2));
rm = b.a*(1 - b.e*cos(E));
R  = rot_mat(b);
rv = R * [rm*cos(nu); rm*sin(nu); 0];
end

%% ── Orbital velocity ────────────────────────────────────────────────────
function vv = vel_at(b, t, mu)
n  = sqrt(mu / b.a^3);
M  = b.M0 + n*(t - b.epoch);
E  = kepler(M, b.e);
nu = 2*atan2(sqrt(1+b.e)*sin(E/2), sqrt(1-b.e)*cos(E/2));
h  = sqrt(mu * b.a*(1-b.e^2));
R  = rot_mat(b);
vv = R * [-(mu/h)*sin(nu); (mu/h)*(b.e+cos(nu)); 0];
end

%% ── Kepler equation (Newton-Raphson) ────────────────────────────────────
function E = kepler(M, e)
E = M;
if e >= 0.8, E = pi; end
for k = 1:50
    dE = (E - e*sin(E) - M) / (1 - e*cos(E));
    E  = E - dE;
    if abs(dE) < 1e-10, return; end
end
end

%% ── Rotation matrix (orbital -> heliocentric) ───────────────────────────
function R = rot_mat(b)
cO=cos(b.Omega); sO=sin(b.Omega);
ci=cos(b.i);     si=sin(b.i);
cw=cos(b.omega); sw=sin(b.omega);
R = [cO*cw-sO*ci*sw,  -cO*sw-sO*ci*cw,  sO*si;
     sO*cw+cO*ci*sw,  -sO*sw+cO*ci*cw, -cO*si;
     si*sw,             si*cw,            ci  ];
end

%% ── Stumpff functions ───────────────────────────────────────────────────
function c = C2(psi)
if     psi >  1e-6,  c = (1 - cos(sqrt(psi))) / psi;
elseif psi < -1e-6,  c = (cosh(sqrt(-psi)) - 1) / (-psi);
else,                c = 0.5;
end
end

function c = C3(psi)
if psi > 1e-6
    s = sqrt(psi);   c = (s - sin(s)) / (psi*s);
elseif psi < -1e-6
    s = sqrt(-psi);  c = (sinh(s) - s) / ((-psi)*s);
else
    c = 1/6;
end
end

%% ── Lambert solver (universal variables) ────────────────────────────────
function [v1, v2] = lambert_solve(r1v, r2v, tof, mu)
r1 = norm(r1v); r2 = norm(r2v);
cd = max(-1, min(1, dot(r1v,r2v)/(r1*r2)));
cz = r1v(1)*r2v(2) - r1v(2)*r2v(1);
dnu = acos(cd);
if cz < 0, dnu = 2*pi - dnu; end
A = sin(dnu)*sqrt(r1*r2 / (1-cd));
if abs(A) < 1e-14, error('Degenerate Lambert problem'); end

psi=0; psi_hi=4*pi^2; psi_lo=-4*pi^2;
for lam_iter = 1:100
    c2 = C2(psi); c3 = C3(psi);
    yn = r1 + r2 + A*(psi*c3-1)/sqrt(c2);
    if yn < 0
        for adj = 1:2000
            psi = psi + 0.1;
            c2=C2(psi); c3=C3(psi);
            yn = r1+r2+A*(psi*c3-1)/sqrt(c2);
            if yn >= 0, break; end
        end
    end
    xi  = sqrt(yn/c2);
    tn  = (xi^3*c3 + A*sqrt(yn)) / sqrt(mu);
    if abs(tn-tof) < 1e-8*abs(tof), break; end
    if tn <= tof, psi_lo=psi; else, psi_hi=psi; end
    dt = (xi^3*(C3(psi)-3*c3*C2(psi)/(2*c2))/(2*c2) + ...
          (A/8)*(3*c3*sqrt(yn)/c2 + A/xi)) / sqrt(mu);
    if abs(dt) > 1e-14
        pn = psi + (tof-tn)/dt;
        if pn>=psi_lo && pn<=psi_hi, psi=pn;
        else, psi=(psi_hi+psi_lo)/2; end
    else
        psi = (psi_hi+psi_lo)/2;
    end
end
f  = 1 - yn/r1; gd = 1 - yn/r2;
g  = A*sqrt(yn/mu);
if abs(g) < 1e-14, error('Lambert: g near zero'); end
v1 = (r2v - f*r1v) / g;
v2 = (gd*r2v - r1v) / g;
end

%% ── Delta-v for a transfer leg ──────────────────────────────────────────
function dv = compute_dv(bi, bj, Td, Tt, p)
dv = 1e6;
if Tt < 0.3, return; end
try
    r1  = pos_at(bi, Td,    p.mu_sun);
    r2  = pos_at(bj, Td+Tt, p.mu_sun);
    v1o = vel_at(bi, Td,    p.mu_sun);
    v2o = vel_at(bj, Td+Tt, p.mu_sun);
    [v1t, v2t] = lambert_solve(r1, r2, Tt, p.mu_sun);
    conv = p.AU_to_km / p.TU_to_sec;
    if strcmp(bi.name,'Earth')
        dv1 = earth_dv(norm((v1t-v1o)*conv), p);
    else
        dv1 = norm(v1t-v1o)*conv;
    end
    if strcmp(bj.name,'Earth')
        dv2 = earth_dv(norm((v2o-v2t)*conv), p);
    else
        dv2 = norm(v2o-v2t)*conv;
    end
    dv = dv1 + dv2;
    if ~isfinite(dv), dv=1e6; end
catch
    dv = 1e6;
end
end

function dv = earth_dv(vinf, p)
vp = sqrt(p.mu_earth / p.r0_park);
vd = sqrt(vinf^2 + 2*p.mu_earth / p.r0_park);
dv = abs(vd - vp);
end

%% ── Build index sets and node mapping ───────────────────────────────────
function [sets, n2b, n2n] = build_sets(p, ref_b, mine_b, earth)
nb    = p.n_bv;
nr    = p.n_rv;
nref  = length(ref_b);
nmine = length(mine_b);

Bs = 0:nb;
Be = (nb+1):(2*nb+1);
R0 = (2*nb+2):(2*nb+nref+1);
Rv = (2*nb+nref+2):(2*nb+nref*nr+1);
R  = [R0, Rv];
M  = (2*nb+nref*nr+2):(2*nb+nref*nr+nmine+1);
V  = [R, M];

% k_prime: starting base -> ending base
kp = containers.Map('KeyType','int32','ValueType','int32');
for k = Bs
    kp(int32(k)) = k + nb + 1;
end

sets.Bs=Bs; sets.Be=Be; sets.R0=R0; sets.Rv=Rv;
sets.R=R;   sets.M=M;   sets.V=V;   sets.kp=kp;

% Node -> body / name maps
n2b = containers.Map('KeyType','int32','ValueType','any');
n2n = containers.Map('KeyType','int32','ValueType','char');
for nd = [Bs, Be]
    n2b(int32(nd)) = earth;
    n2n(int32(nd)) = 'Earth';
end
for idx = 1:length(R)
    orig = mod(idx-1, nref) + 1;
    n2b(int32(R(idx))) = ref_b{orig};
    n2n(int32(R(idx))) = ref_b{orig}.name;
end
for idx = 1:length(M)
    n2b(int32(M(idx))) = mine_b{idx};
    n2n(int32(M(idx))) = mine_b{idx}.name;
end
end

%% ── Mass ratio initialization (2D grid scan, no optimizer) ──────────────
function mr = init_mass_ratios(p, sets, n2b)
fprintf('Initializing mass ratios (grid scan)...\n');
src = [sets.Bs, sets.V];
dst = [sets.V,  sets.Be];

Td_grid = 0:2:12;   % departure times to check
Tt_grid = 1:2:13;   % transfer times to check

pair_cache = containers.Map('KeyType','char','ValueType','double');
mr         = containers.Map('KeyType','char','ValueType','double');

for i = src
    for j = dst
        if i == j, continue; end
        bi  = n2b(int32(i));
        bj  = n2b(int32(j));
        key = sprintf('%d|%d', i, j);
        pk  = sprintf('%s|%s', bi.name, bj.name);

        if strcmp(bi.name, bj.name)
            mr(key) = 0.999; continue;
        end
        if isKey(pair_cache, pk)
            mr(key) = pair_cache(pk); continue;
        end

        best = 1e6;
        for Td = Td_grid
            for Tt = Tt_grid
                dv = compute_dv(bi, bj, Td, Tt, p);
                if isfinite(dv) && dv < best
                    best = dv;
                end
            end
        end

        if isfinite(best) && best > 0 && best < 50
            m = exp(-best / (p.g0 * p.I_sp));
            if isfinite(m) && m > 0.001 && m <= 1
                mr(key) = m;
            else
                mr(key) = 0.05;
            end
        else
            mr(key) = 0.05;
        end
        pair_cache(pk) = mr(key);
    end
end

vals = cell2mat(values(mr));
vals = vals(vals < 0.99);
fprintf('  Done. Range: [%.4f, %.4f]\n', min(vals), max(vals));
end

function v = get_mr(mr, i, j)
key = sprintf('%d|%d', i, j);
if isKey(mr, key), v = mr(key);
else,              v = 0.05;
end
end

%% ── Trajectory segment optimizer (NLP via fmincon) ──────────────────────
function res = opt_segment(bi, bj, T_arr, p)
Td_lo = T_arr + p.T_service;
at    = (bi.a + bj.a) / 2;
Tt0   = max(0.5, min(15, pi*sqrt(at^3 / p.mu_sun)));

obj_fn = @(x) compute_dv(bi, bj, x(1), x(2), p);
lb = [Td_lo, 0.5];
ub = [Td_lo + 3, 15];
opts = optimoptions('fmincon', ...
    'Algorithm','trust-region-reflective', ...
    'Display','off', ...
    'MaxIterations', 200, ...
    'FunctionTolerance', 1e-6);

x0_list = [Td_lo, Tt0;
            Td_lo, 2.0;
            Td_lo, 6.0;
            Td_lo, 10.0];

best_dv = 1e6;
best_x  = [Td_lo, Tt0];
for k = 1:size(x0_list, 1)
    x0 = [max(lb(1),min(ub(1),x0_list(k,1))), ...
          max(lb(2),min(ub(2),x0_list(k,2)))];
    try
        [x, fv] = fmincon(obj_fn, x0, [], [], [], [], lb, ub, [], opts);
        if isfinite(fv) && fv < best_dv
            best_dv = fv; best_x = x;
        end
    catch
    end
end

res.Td = best_x(1);
res.Tt = best_x(2);
res.dv = best_dv;
res.Ta = best_x(1) + best_x(2);
if best_dv < 100
    res.mr = exp(-best_dv / (p.g0 * p.I_sp));
else
    res.mr = 1e-10;
end
end

%% ── Build MILP (Gurobi) ─────────────────────────────────────────────────
function [gm, vi] = build_milp(p, sets, mr)
Bs=sets.Bs; V=sets.V; R=sets.R; M=sets.M; Be=sets.Be; kp=sets.kp;
md=p.m_dry; mm=p.m_max; qm=p.q_max;
lam=p.lambda; mm_=p.m_mine; pr=p.profit;

xk = @(k,i,j) sprintf('x%d_%d_%d',k,i,j);
yk = @(k,i)   sprintf('y%d_%d',k,i);

%-- Variable index maps -----------------------------------------------
vi.x = containers.Map('KeyType','char',  'ValueType','int32');
vi.u = containers.Map('KeyType','int32', 'ValueType','int32');
vi.q = containers.Map('KeyType','int32', 'ValueType','int32');
vi.r = containers.Map('KeyType','int32', 'ValueType','int32');
vi.y = containers.Map('KeyType','char',  'ValueType','int32');
nv = 0;

for k = Bs
    for j = V,  nv=nv+1; vi.x(xk(k,k,j))=nv; end
    kpk = kp(int32(k));
    for i = V
        for j = V
            if i~=j, nv=nv+1; vi.x(xk(k,i,j))=nv; end
        end
        nv=nv+1; vi.x(xk(k,i,kpk))=nv;
    end
end
nx = nv;
for i=[Bs,V], nv=nv+1; vi.u(int32(i))=nv; end
for i=V,      nv=nv+1; vi.q(int32(i))=nv; end
for i=R,      nv=nv+1; vi.r(int32(i))=nv; end
for k=Bs, for i=V, nv=nv+1; vi.y(yk(k,i))=nv; end, end
N = nv;

%-- Variable bounds and types ----------------------------------------
lb    = zeros(N,1);
ub    = zeros(N,1);
vtype = repmat('C',1,N);
obj   = zeros(N,1);

for idx=1:nx,   ub(idx)=1; vtype(idx)='B'; end   % x: binary
for i=[Bs,V],   ub(vi.u(int32(i)))=mm; end         % u: [0,mm]
for i=V,        ub(vi.q(int32(i)))=qm; end         % q: [0,qm]
for i=R,        ub(vi.r(int32(i)))=mm; end         % r: [0,mm]
for k=Bs, for i=V, ub(vi.y(yk(k,i)))=qm; end, end % y: [0,qm]

% Physical limit: u[i]+m_mine <= m_max for mining nodes
for i=M, ub(vi.u(int32(i))) = mm - mm_; end

%-- Objective (Eq.10) -------------------------------------------------
% +profit per arc leaving a mining node
for i = M
    for k = Bs
        kpk = kp(int32(k));
        for j = V
            if i~=j && isKey(vi.x,xk(k,i,j))
                obj(vi.x(xk(k,i,j))) = obj(vi.x(xk(k,i,j))) + pr;
            end
        end
        if isKey(vi.x,xk(k,i,kpk))
            obj(vi.x(xk(k,i,kpk))) = obj(vi.x(xk(k,i,kpk))) + pr;
        end
    end
end
% -lambda*u[k] + lambda*m_dry*x[k,k,j]
for k = Bs
    obj(vi.u(int32(k))) = obj(vi.u(int32(k))) - lam;
    for j = V
        if isKey(vi.x,xk(k,k,j))
            obj(vi.x(xk(k,k,j))) = obj(vi.x(xk(k,k,j))) + lam*md;
        end
    end
end
% -lambda*r[i]
for i = R
    obj(vi.r(int32(i))) = obj(vi.r(int32(i))) - lam;
end

%-- Constraint accumulator -------------------------------------------
ri=[]; ci=[]; vv=[]; rhs=[]; sense=''; nc=0;

% Helper: append one constraint row
% cols = variable indices, vals = coefficients, b = rhs, s = sense char
    function append(cols, vals, b, s)
        n   = length(cols);
        nc  = nc + 1;
        ri  = [ri,  repmat(nc, 1, n)];
        ci  = [ci,  cols];
        vv  = [vv,  vals];
        rhs = [rhs, b];
        sense(end+1) = s;
    end

%-- (C1) Total spacecraft deployed <= 1 ------------------------------
c=[]; v=[];
for k=Bs, for j=V
    if isKey(vi.x,xk(k,k,j)), c(end+1)=vi.x(xk(k,k,j)); v(end+1)=1; end
end, end
append(c,v,1,'<');

%-- (C2) Each base deploys <= 1 --------------------------------------
for k=Bs
    c=[]; v=[];
    for j=V
        if isKey(vi.x,xk(k,k,j)), c(end+1)=vi.x(xk(k,k,j)); v(end+1)=1; end
    end
    if ~isempty(c), append(c,v,1,'<'); end
end

%-- (C3) Each refueling node visited <= 1 time -----------------------
for j=R
    c=[]; v=[];
    for k=Bs
        if isKey(vi.x,xk(k,k,j)), c(end+1)=vi.x(xk(k,k,j)); v(end+1)=1; end
        for i=V
            if i~=j && isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=1; end
        end
    end
    if ~isempty(c), append(c,v,1,'<'); end
end

%-- (C4) Each mining node visited <= 1 time --------------------------
for i=M
    c=[]; v=[];
    for k=Bs
        kpk=kp(int32(k));
        for j=V
            if i~=j && isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=1; end
        end
        if isKey(vi.x,xk(k,i,kpk)), c(end+1)=vi.x(xk(k,i,kpk)); v(end+1)=1; end
    end
    if ~isempty(c), append(c,v,1,'<'); end
end

%-- (C5) Flow conservation for each node under each spacecraft --------
for j=V
    for k=Bs
        kpk=kp(int32(k));
        c=[]; v=[];
        if isKey(vi.x,xk(k,k,j)), c(end+1)=vi.x(xk(k,k,j)); v(end+1)=1;  end
        if isKey(vi.x,xk(k,j,kpk)), c(end+1)=vi.x(xk(k,j,kpk)); v(end+1)=-1; end
        for i=V
            if i~=j
                if isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=1;  end
                if isKey(vi.x,xk(k,j,i)), c(end+1)=vi.x(xk(k,j,i)); v(end+1)=-1; end
            end
        end
        if ~isempty(c), append(c,v,0,'='); end
    end
end

%-- (C6) Mass flow: base k -> j: u[j] - mr*u[k] + mm*x <= mm --------
for k=Bs
    for j=V
        if ~isKey(vi.x,xk(k,k,j)), continue; end
        m = get_mr(mr,k,j);
        append([vi.u(int32(j)), vi.u(int32(k)), vi.x(xk(k,k,j))], ...
               [1, -m, mm], mm, '<');
    end
end

%-- (C7) Mass flow: mining i -> j: u[j]-mr*u[i]+mm*sum_x <= mm+mr*mm_
for i=M
    for j=V
        if i==j, continue; end
        m=get_mr(mr,i,j);
        c=[vi.u(int32(j)), vi.u(int32(i))]; v=[1,-m];
        for k=Bs
            if isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=mm; end
        end
        append(c,v,mm+m*mm_,'<');
    end
end

%-- (C8) Mass flow: refuel i -> j: u[j]-mr*(u[i]+r[i])+mm*sum_x <= mm
for i=R
    for j=V
        if i==j, continue; end
        m=get_mr(mr,i,j);
        c=[vi.u(int32(j)), vi.u(int32(i)), vi.r(int32(i))]; v=[1,-m,-m];
        for k=Bs
            if isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=mm; end
        end
        append(c,v,mm,'<');
    end
end

%-- (C9) Mining i -> ending base: -mr*u[i]+mm*x <= mm-md+mr*mm_ ------
for i=M
    for k=Bs
        kpk=kp(int32(k));
        if ~isKey(vi.x,xk(k,i,kpk)), continue; end
        m=get_mr(mr,i,kpk);
        append([vi.u(int32(i)), vi.x(xk(k,i,kpk))], [-m,mm], mm-md+m*mm_,'<');
    end
end

%-- (C10) Refuel i -> ending base: -mr*(u[i]+r[i])+mm*x <= mm-md -----
for i=R
    for k=Bs
        kpk=kp(int32(k));
        if ~isKey(vi.x,xk(k,i,kpk)), continue; end
        m=get_mr(mr,i,kpk);
        append([vi.u(int32(i)), vi.r(int32(i)), vi.x(xk(k,i,kpk))], ...
               [-m,-m,mm], mm-md,'<');
    end
end

%-- (C11) Cumulative mining: q[j] >= mm_ - qm*(1-x[k,k,j])
%         => -q[j] + qm*x[k,k,j] <= qm - mm_
for j=M
    for k=Bs
        if ~isKey(vi.x,xk(k,k,j)), continue; end
        append([vi.q(int32(j)), vi.x(xk(k,k,j))], [-1,qm], qm-mm_,'<');
    end
end

%-- (C12) q[j] >= q[i]+mm_ - qm*(1-sum_x): -q[j]+q[i]+qm*sum_x <= qm-mm_
for i=V
    for j=M
        if i==j, continue; end
        c=[vi.q(int32(j)), vi.q(int32(i))]; v=[-1,1];
        for k=Bs
            if isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=qm; end
        end
        append(c,v,qm-mm_,'<');
    end
end

%-- (C13) q[j] >= q[i] - qm*(1-sum_x) for refuel j: -q[j]+q[i]+qm*sum_x <= qm
for i=V
    for j=R
        if i==j, continue; end
        c=[vi.q(int32(j)), vi.q(int32(i))]; v=[-1,1];
        for k=Bs
            if isKey(vi.x,xk(k,i,j)), c(end+1)=vi.x(xk(k,i,j)); v(end+1)=qm; end
        end
        append(c,v,qm,'<');
    end
end

%-- (C14) Physical limits for mining nodes: -u[i]+q[i] <= -(md-mm_)
for i=M
    append([vi.u(int32(i)), vi.q(int32(i))], [-1,1], -(md-mm_),'<');
end

%-- (C15) Physical limits for refueling nodes: -u[i]+q[i] <= -md
for i=R
    append([vi.u(int32(i)), vi.q(int32(i))], [-1,1], -md,'<');
end

%-- Assemble Gurobi model --------------------------------------------
gm.obj        = obj;
gm.lb         = lb;
gm.ub         = ub;
gm.vtype      = vtype;
gm.A          = sparse(double(ri), double(ci), double(vv), nc, N);
gm.rhs        = rhs(:);
gm.sense      = sense;
gm.modelsense = 'max';
end

%% ── Extract routes from Gurobi solution ─────────────────────────────────
function routes = extract_routes(xsol, vi, sets)
Bs=sets.Bs; V=sets.V; Be=sets.Be; kp=sets.kp;
xk = @(k,i,j) sprintf('x%d_%d_%d',k,i,j);
routes = {};

for k = Bs
    route   = k;
    current = k;
    visited = containers.Map('KeyType','int32','ValueType','logical');
    visited(int32(k)) = true;

    for step = 1:length(V)+2
        nxt = [];
        % Look for active arc from current to any V node
        for j = V
            key = xk(k, current, j);
            if isKey(vi.x,key) && xsol(vi.x(key)) > 0.5
                nxt = j; break;
            end
        end
        % Check arc to ending base
        if isempty(nxt)
            kpk = kp(int32(k));
            key = xk(k, current, kpk);
            if isKey(vi.x,key) && xsol(vi.x(key)) > 0.5
                route(end+1) = kpk;
            end
            break;
        end
        if isKey(visited,int32(nxt)) && ~ismember(nxt,Be), break; end
        visited(int32(nxt)) = true;
        route(end+1) = nxt;
        if ismember(nxt, Be), break; end
        current = nxt;
    end

    if length(route) > 2
        routes{end+1} = route;
    end
end
end

%% ── Iterative MILP-NLP solver ───────────────────────────────────────────
function sol = solve_vrtpp(p, sets, n2b, n2n, maxiter, tol)
fprintf('================================================================================\n');
fprintf('STARTING VRTPP-PR OPTIMIZATION\n');
fprintf('================================================================================\n');

mr = init_mass_ratios(p, sets, n2b);

% Print critical mass ratios for paper route
fprintf('\nCritical mass ratios (Earth->FG3->Bennu->Earth):\n');
all_nodes = [sets.Bs, sets.V];
for i = all_nodes
    for j = [sets.V, sets.Be]
        ni = n2n(int32(i)); nj = n2n(int32(j));
        is_crit = (contains(ni,'Earth') && contains(nj,'FG3'))  || ...
                  (contains(ni,'FG3')   && contains(nj,'Bennu'))|| ...
                  (contains(ni,'Bennu') && contains(nj,'Earth'));
        if is_crit
            m  = get_mr(mr,i,j);
            dv = -log(max(m,1e-10)) * p.g0 * p.I_sp;
            fprintf('  (%2d,%2d) %-20s -> %-20s: mr=%.4f, dv~%.1f km/s\n', ...
                    i,j,ni,nj,m,dv);
        end
    end
end

dv_mat = containers.Map('KeyType','char','ValueType','double');
Td_mat = containers.Map('KeyType','char','ValueType','double');
Tt_mat = containers.Map('KeyType','char','ValueType','double');
prev_routes = {};
routes      = {};

gp.OutputFlag = 0;
gp.MIPGap     = 0.03;
gp.TimeLimit  = 100;
t0 = tic;

for iter = 1:maxiter
    fprintf('\n================================================================================\n');
    fprintf('ITERATION %d\n', iter);
    fprintf('================================================================================\n');

    fprintf('[MILP] Building model...\n');
    [gm, vi] = build_milp(p, sets, mr);
    fprintf('[MILP] Solving...\n');
    res = gurobi(gm, gp);

    ok_status = strcmp(res.status,'OPTIMAL') || ...
                strcmp(res.status,'SUBOPTIMAL') || ...
                strcmp(res.status,'TIME_LIMIT');
    if ~ok_status || ~isfield(res,'x')
        fprintf('[MILP] Status: %s -- stopping.\n', res.status);
        if iter==1, sol=[]; return; end
        break;
    end

    fprintf('[MILP] Objective: %.4f\n', res.objval);
    routes = extract_routes(res.x, vi, sets);
    fprintf('[MILP] Routes: %d spacecraft\n', length(routes));
    for r = 1:length(routes)
        nm = cellfun(@(nd) n2n(int32(nd)), num2cell(routes{r}), 'UniformOutput',false);
        fprintf('  Spacecraft %d: %s\n', r, strjoin(nm,' -> '));
    end
    if isempty(routes), break; end

    % NLP trajectory optimization
    fprintf('\n[NLP] Optimizing trajectories...\n');
    old_dv = dv_mat;
    for r = 1:length(routes)
        rt    = routes{r};
        T_arr = 0;
        for s = 1:length(rt)-1
            ni = rt(s); nj = rt(s+1);
            bi = n2b(int32(ni)); bj = n2b(int32(nj));
            fprintf('  %s -> %s... ', n2n(int32(ni)), n2n(int32(nj)));
            seg = opt_segment(bi, bj, T_arr, p);
            key = sprintf('%d|%d', ni, nj);
            dv_mat(key) = seg.dv;
            Td_mat(key) = seg.Td;
            Tt_mat(key) = seg.Tt;
            mr(key)     = seg.mr;
            % Propagate refined mr to same-body pairs (conservative)
            all_nd = [sets.Bs, sets.V, sets.Be];
            for ii = all_nd
                for jj = all_nd
                    if ii==ni && jj==nj, continue; end
                    if ~isKey(n2b,int32(ii))||~isKey(n2b,int32(jj)), continue; end
                    same_bi = strcmp(n2b(int32(ii)).name, bi.name);
                    same_bj = strcmp(n2b(int32(jj)).name, bj.name);
                    if same_bi && same_bj
                        k2 = sprintf('%d|%d',ii,jj);
                        if ~isKey(mr,k2) || mr(k2)>seg.mr
                            mr(k2) = seg.mr;
                        end
                    end
                end
            end
            T_arr = seg.Ta;
            fprintf('dv=%.2f km/s,  Td=%.2f TU,  Tt=%.2f TU\n', ...
                    seg.dv, seg.Td, seg.Tt);
        end
    end

    % Convergence check
    if iter > 1
        route_match = (length(routes)==length(prev_routes));
        if route_match
            for r=1:length(routes)
                if ~isequal(routes{r},prev_routes{r}), route_match=false; break; end
            end
        end
        if ~route_match
            fprintf('\n[CONVERGENCE] Route changed, continuing...\n');
        else
            common = intersect(keys(dv_mat), keys(old_dv));
            if ~isempty(common)
                diff_sq=0; max_old=0;
                for k2=1:length(common)
                    diff_sq = diff_sq + (dv_mat(common{k2})-old_dv(common{k2}))^2;
                    max_old = max(max_old, abs(old_dv(common{k2})));
                end
                chg = sqrt(diff_sq) / max(max_old,1e-10);
                fprintf('\n[CONVERGENCE] dv change: %f  (tol: %f)\n', chg, tol);
                if chg < tol
                    fprintf('\n================================================================================\n');
                    fprintf('CONVERGED after %d iterations!\n', iter);
                    fprintf('================================================================================\n');
                    break;
                end
            end
        end
    end
    prev_routes = routes;
end

sol.iter   = iter;
sol.time   = toc(t0);
sol.obj    = res.objval;
sol.routes = routes;
sol.dv     = dv_mat;
sol.Td     = Td_mat;
sol.Tt     = Tt_mat;
sol.mr     = mr;
end

%% ── Display results ─────────────────────────────────────────────────────
function display_results(sol, n2n, p)
fprintf('\n================================================================================\n');
fprintf('FINAL SOLUTION\n');
fprintf('================================================================================\n');
fprintf('Iterations : %d\n', sol.iter);
fprintf('Time       : %.1f s\n', sol.time);
fprintf('Objective  : %.4f\n', sol.obj);
fprintf('\nROUTES AND TRAJECTORIES\n%s\n', repmat('-',1,70));
for r = 1:length(sol.routes)
    rt = sol.routes{r};
    nm = cellfun(@(nd) n2n(int32(nd)), num2cell(rt), 'UniformOutput',false);
    fprintf('\nSpacecraft %d: %s\n', r, strjoin(nm,' -> '));
    tot=0;
    for s = 1:length(rt)-1
        key = sprintf('%d|%d',rt(s),rt(s+1));
        if isKey(sol.dv,key)
            dv=sol.dv(key); Td=sol.Td(key); Tt=sol.Tt(key);
            fprintf('  %-20s -> %-20s: dv=%.2f km/s, Td=%.2f, Tt=%.2f TU\n', ...
                    n2n(int32(rt(s))), n2n(int32(rt(s+1))), dv, Td, Tt);
            tot=tot+dv;
        end
    end
    fprintf('  Total delta-v: %.2f km/s\n', tot);
end
fprintf('\n%s\nPAPER TABLE 5 REFERENCE\n%s\n', repmat('-',1,70),repmat('-',1,70));
fprintf('  Earth  -> 1996 FG3     :  9.51 km/s  (Td=0.09, Tt=6.26 TU)\n');
fprintf('  FG3    -> 101955 Bennu :  7.32 km/s  (Td=8.83, Tt=7.06 TU)\n');
fprintf('  Bennu  -> Earth        :  8.17 km/s  (Td=17.59,Tt=6.81 TU)\n');
end
