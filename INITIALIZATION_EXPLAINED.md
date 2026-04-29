# How the Initialization and Warm-Start Work

## The core problem

The optimizer needs to know, before it picks a route, roughly how expensive each possible transfer is. "Expensive" here means ΔV — the rocket fuel needed to travel from asteroid A to asteroid B.

The trouble is that ΔV between two bodies is not a fixed number. It depends on *when* you leave (departure time T_d) and *how long* the trip takes (transfer time T_t). If you leave at the wrong time or take a badly-timed path, the same journey can cost 5 km/s or 40 km/s. The pork chop plots from the verification step make this very visible — ΔV varies wildly across the (T_d, T_t) space.

So before the main loop can run, we need a reasonable ΔV estimate for every arc the spacecraft might fly. That is what `initialize_mass_ratios` does.

---

## Step 1: The coarse grid scan

The function loops over every possible (departure body → arrival body) pair and tries a grid of departure and transfer times:

- Departure times: 0, 1, 2, … 13 TU (one per year, roughly)
- Transfer times: 1, 3, 5, 7, 9, 11, 13 TU (every other value)

That is 14 × 7 = 98 combinations per pair. For each one it calls the Lambert solver to compute the actual ΔV. It keeps whichever (T_d, T_t) pair gave the lowest ΔV.

**Why do a grid at all?** Because the ΔV landscape has multiple valleys — local minima. If you just hand the optimizer one starting guess and let it roll downhill, it will find the nearest valley, which may not be the deepest one. The grid is a cheap way to survey the whole landscape and find which valley looks most promising before committing.

---

## Step 2: The L-BFGS-B refiner

Once the grid finds the best cell, the resolution is only as good as the grid spacing (1 TU × 2 TU). The true minimum might sit between grid points. So the code hands that best grid point to a mathematical optimizer — L-BFGS-B — which uses gradient information to walk to the precise local minimum nearby.

**What is L-BFGS-B?** It is a standard gradient-based optimization algorithm. "L-BFGS" stands for Limited-memory Broyden–Fletcher–Goldfarb–Shanno, which is a method for approximating the curvature of the objective function without storing a full matrix. The "B" means it respects bounds (T_d ≥ 0, T_t > 0). In plain terms: it takes small steps in the direction that reduces ΔV fastest, using an approximation of the local shape of the ΔV surface to take smarter steps than a simple gradient descent would.

**Why L-BFGS-B here and not the same solver used in the main loop?** The main loop uses `trust-constr`, which is slower but handles constraints more carefully. For initialization we just want a quick, unconstrained refinement of a grid point — L-BFGS-B is faster for that.

The result of this step is a (T_d, T_t) pair and a ΔV value that is close to the true local minimum in that basin.

---

## Step 3: Converting ΔV to a mass ratio

The MILP does not actually work with ΔV directly. It works with **mass ratios** — the fraction of mass a spacecraft retains after a burn. The conversion is the Tsiolkovsky rocket equation:

```
mass_ratio = exp( -ΔV / (g0 × Isp) )
```

A mass ratio of 1.0 means no fuel was spent. A ratio of 0.5 means the spacecraft burned half its mass as propellant. The MILP uses these ratios to track how much fuel is left at each step of the route.

---

## What the main loop does with all this

After initialization, the main loop alternates between two steps:

**MILP step:** Given the current mass ratios (one per arc), solve the routing problem. Which sequence of asteroids, with which spacecraft, maximizes profit while respecting fuel and time constraints? This is a combinatorial problem — Gurobi searches over all valid integer combinations of arcs.

**NLP step:** Given the route the MILP just chose, re-optimize the timing (T_d, T_t) on each leg of that specific route. Now that we know exactly which arcs will be flown, we can refine their ΔV estimates more carefully. This updates the mass ratios for the next MILP solve.

The two steps feed each other until the route stops changing and the ΔV values stabilize. That is convergence.

---

## The warm-start

Each time the NLP step runs, it saves the (T_d, T_t) it found for each arc. On the next iteration, when the same arc appears in the route again, the NLP starts from the previous answer rather than from scratch. This is the warm-start.

**Why does this matter?** The NLP is a local optimizer — it finds the nearest minimum to wherever it starts. If it starts from the same point each iteration, it will find the same minimum each time, which is what you want for stable convergence. Without warm-starting, the NLP might drift to a different local minimum on some iterations, causing the ΔV estimates to oscillate and the algorithm to never converge.

The same idea applies to the MILP: at the start of each iteration, the binary variables from the previous solution are passed as `Start` hints to Gurobi. This tells Gurobi "the answer probably looks like this" and lets it find the optimal solution faster.

---

## Why 22 iterations?

The algorithm converges when two conditions are both met:
1. The route (the sequence of asteroids visited) has not changed
2. The total ΔV on the active route has changed by less than 0.1% from the previous iteration

Early iterations tend to change the route as the MILP sees increasingly accurate mass ratios and switches to better arcs. Later iterations keep the same route but refine the timing. The NLP oscillates slightly between local minima on some legs (as the verification showed), which keeps the ΔV change above the convergence threshold — hence 22 iterations rather than 5 or 6.

---

## The known weakness

The grid in Step 1 covers T_t only up to 13 TU in steps of 2 TU. For some body pairs the true global minimum sits in a basin the grid never samples — for example the Earth → Anteros leg has its global minimum around T_t ≈ 7 TU but the grid may land in a shallower basin at T_t ≈ 2 TU. The L-BFGS-B refiner then polishes that shallow basin and never discovers the deeper one. This is the root cause of the 2–4 km/s local-minimum errors identified in the verification.
