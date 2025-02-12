import random
import time
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum, multidict

class ComplexProductionScheduling:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        if seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# data generation #################
    def randint(self, size, interval):
        return np.random.randint(interval[0], interval[1], size)

    def generate_instance(self):
        demands = self.randint(self.n_customers, self.demand_interval)
        capacities = self.randint(self.n_facilities, self.capacity_interval)
        fixed_costs = (
            self.randint(self.n_facilities, self.fixed_cost_scale_interval) * np.sqrt(capacities) +
            self.randint(self.n_facilities, self.fixed_cost_cste_interval)
        )
        production_costs = self.unit_production_costs() * demands[:, np.newaxis]

        capacities = capacities * self.ratio * np.sum(demands) / np.sum(capacities)
        capacities = np.round(capacities)
        
        energy_costs = self.generate_energy_costs()

        res = {
            'demands': demands,
            'capacities': capacities,
            'fixed_costs': fixed_costs,
            'production_costs': production_costs,
            'energy_costs': energy_costs,
        }
        res['cliques'] = self.generate_cliques()
        return res

    def unit_production_costs(self):
        scaling = 10.0
        rand = lambda n, m: np.random.rand(n, m)
        costs = scaling * np.sqrt(
            (rand(self.n_customers, 1) - rand(1, self.n_facilities))**2 +
            (rand(self.n_customers, 1) - rand(1, self.n_facilities))**2
        )
        return costs
        
    def generate_energy_costs(self):
        return self.randint(self.n_facilities, self.energy_cost_interval)

    def generate_cliques(self):
        G = nx.barabasi_albert_graph(self.n_facilities, self.clique_connections)
        cliques = list(nx.find_cliques(G))
        return cliques

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        demands = instance['demands']
        capacities = instance['capacities']
        fixed_costs = instance['fixed_costs']
        production_costs = instance['production_costs']
        energy_costs = instance['energy_costs']
        cliques = instance['cliques']

        n_customers = len(demands)
        n_facilities = len(capacities)

        model = Model("ComplexProductionScheduling")

        # Decision variables
        open_facilities = {j: model.addVar(vtype="B", name=f"Open_{j}") for j in range(n_facilities)}
        serve = {(i, j): model.addVar(vtype="I", name=f"Serve_{i}_{j}") for i in range(n_customers) for j in range(n_facilities)}
        shift = {(j, t): model.addVar(vtype="B", name=f"Shift_{j}_{t}") for j in range(n_facilities) for t in range(self.n_shifts)}
        energy_use = {(j, t): model.addVar(vtype="C", name=f"EnergyUse_{j}_{t}") for j in range(n_facilities) for t in range(self.n_shifts)}

        # Add new clique indicator variables
        clique_indicators = {k: model.addVar(vtype="B", name=f"CliqueIndicator_{k}") for k in range(len(cliques))}

        # New downtime variables
        downtime = {j: model.addVar(vtype="C", name=f"Downtime_{j}") for j in range(n_facilities)}

        # Objective: Minimize the total cost
        objective_expr = quicksum(fixed_costs[j] * open_facilities[j] for j in range(n_facilities)) + \
                         quicksum(production_costs[i, j] * serve[i, j] for i in range(n_customers) for j in range(n_facilities)) + \
                         quicksum(energy_costs[j] * energy_use[j, t] for j in range(n_facilities) for t in range(self.n_shifts)) + \
                         quicksum(self.downtime_costs[j] * downtime[j] for j in range(n_facilities))

        # Constraints: Demand must be met
        for i in range(n_customers):
            model.addCons(quicksum(serve[i, j] for j in range(n_facilities)) >= 1, f"Demand_{i}")

        # Constraints: Capacity limits
        for j in range(n_facilities):
            model.addCons(quicksum(serve[i, j] * demands[i] for i in range(n_customers)) <= capacities[j] * open_facilities[j], f"Capacity_{j}")

        # Constraint: Total facility capacity must cover total demand
        total_demand = np.sum(demands)
        model.addCons(quicksum(capacities[j] * open_facilities[j] for j in range(n_facilities)) >= total_demand, "TotalDemand")

        # Constraint: Forcing assignments to open facilities only
        for i in range(n_customers):
            for j in range(n_facilities):
                model.addCons(serve[i, j] <= open_facilities[j] * self.big_M, f"Tightening_{i}_{j}")

        # New Constraints: Shift limits
        for j in range(n_facilities):
            model.addCons(quicksum(shift[j, t] for t in range(self.n_shifts)) <= self.shift_limit, f"ShiftLimit_{j}")

        # New Constraints: Energy use
        for j in range(n_facilities):
            for t in range(self.n_shifts):
                model.addCons(energy_use[j, t] <= capacities[j] * shift[j, t] * self.big_M, f"EnergyUse_{j}_{t}")

        # New Constraints: Clique inequalities
        for k, clique in enumerate(cliques):
            model.addCons(quicksum(open_facilities[j] for j in clique) - clique_indicators[k] <= len(clique) - 1, f"CliqueCover_{k}")
            for j in clique:
                model.addCons(quicksum(open_facilities[j_prime] for j_prime in clique) - open_facilities[j] <= len(clique) - 1, f"CliqueRelation_{j}_{k}")

        # New Constraints: Downtime limits
        for j in range(n_facilities):
            model.addCons(downtime[j] <= self.max_downtime, f"MaxDowntime_{j}")

        model.setObjective(objective_expr, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_customers': 187,
        'n_facilities': 56,
        'demand_interval': (10, 94),
        'capacity_interval': (90, 1449),
        'fixed_cost_scale_interval': (1250, 1387),
        'fixed_cost_cste_interval': (0, 1),
        'energy_cost_interval': (15, 300),
        'ratio': 75.0,
        'continuous_assignment': 0,
        'n_shifts': 3,
        'shift_limit': 2,
        'clique_connections': 21,
        'big_M': 1000000,
        'downtime_costs': [random.uniform(1, 100) for _ in range(56)], # New
        'max_downtime': 100, # New
    }

    production_scheduling = ComplexProductionScheduling(parameters, seed=seed)
    instance = production_scheduling.generate_instance()
    solve_status, solve_time = production_scheduling.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")