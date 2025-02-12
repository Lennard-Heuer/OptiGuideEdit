import random
import time
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum
from networkx.algorithms import bipartite

class MaxSatisfiability:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_road_network(self, n):
        G = nx.erdos_renyi_graph(n, self.road_connectivity_prob, seed=self.seed)
        return G.edges

    def generate_disaster_impact(self, n):
        return {f'disaster_{i}': np.random.gamma(self.alpha_impact, self.beta_impact, size=n) for i in range(self.num_disaster_types)}

    def generate_weather_data(self, n):
        return {f'weather_{i}': np.random.normal(self.weather_mean, self.weather_std, size=n) for i in range(self.num_weather_types)}

    def generate_instances(self):
        n = np.random.randint(self.min_n, self.max_n + 1)
        road_network = self.generate_road_network(n)
        disaster_impact = self.generate_disaster_impact(n)
        weather_data = self.generate_weather_data(n)

        edges = self.generate_maxsat_graph(n)
        clauses = [(f'v{i},v{j}', 1) for i, j in edges] + [(f'-v{i},-v{j}', 1) for i, j in edges]

        res = {
            'clauses': clauses,
            'road_network': road_network,
            'disaster_impact': disaster_impact,
            'weather_data': weather_data
        }
        
        return res

    def generate_maxsat_graph(self, n):
        divider = np.random.randint(1, 6)
        G = self.generate_bipartite_graph(n // divider, n - n // divider, self.er_prob)

        n_edges = len(G.edges)
        edges = list(G.edges)

        added_edges = 0
        while added_edges < n_edges * self.edge_addition_prob:
            i, j = np.random.randint(0, n), np.random.randint(0, n)
            if (i, j) not in edges and (j, i) not in edges:
                added_edges += 1
                edges.append((i, j))

        return edges

    def generate_bipartite_graph(self, n1, n2, p):
        return bipartite.random_graph(n1, n2, p, seed=self.seed)

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        clauses = instance['clauses']
        road_network = instance['road_network']
        disaster_impact = instance['disaster_impact']
        weather_data = instance['weather_data']

        model = Model("MaxSatisfiability")
        var_names = {}  

        # Create variables for each literal and clause
        for idx, (clause, weight) in enumerate(clauses):
            for var in clause.split(','):
                literal = var[1:] if var.startswith('-') else var
                if literal not in var_names:
                    var_names[literal] = model.addVar(vtype="B", name=literal)
            clause_var = model.addVar(vtype="B", name=f"cl_{idx}")
            var_names[f"cl_{idx}"] = clause_var

        # Objective function - maximize the number of satisfied clauses
        objective_expr = quicksum(
            var_names[f"cl_{idx}"] * weight for idx, (clause, weight) in enumerate(clauses) if weight < np.inf
        )

        # Add constraints for each clause
        for idx, (clause, weight) in enumerate(clauses):
            vars_in_clause = clause.split(',')
            clause_var = var_names[f"cl_{idx}"]

            # Define the positive and negative parts
            positive_part = quicksum(var_names[var] for var in vars_in_clause if not var.startswith('-'))
            negative_part = quicksum(1 - var_names[var[1:]] for var in vars_in_clause if var.startswith('-'))

            # Total satisfied variables in the clause
            total_satisfied = positive_part + negative_part

            if weight < np.inf:
                model.addCons(total_satisfied >= clause_var, name=f"clause_{idx}")
            else:
                model.addCons(total_satisfied >= 1, name=f"clause_{idx}")

        ### new constraints and variables and objective code ends here
        # Variables representing the impact of different disasters on healthcare needs
        disaster_vars = {k: model.addVar(vtype="C", name=f"impact_{k}") for k in disaster_impact.keys()}

        # Dynamic adjustment of deployment based on real-time weather data
        weather_vars = {k: model.addVar(vtype="C", name=f"weather_{k}") for k in weather_data.keys()}

        # Add constraints related to different disaster types' impacts
        for var, impact in disaster_vars.items():
            impact_factor = disaster_impact[var]
            for i in range(len(impact_factor)):
                model.addCons(impact * impact_factor[i] >= var_names[f'v{i}'], name=f"disaster_{var}_impact_{i}")

        # Constraints dynamically adjusting based on weather data
        for var, weather in weather_vars.items():
            weather_factor = weather_data[var]
            for i in range(len(weather_factor)):
                model.addCons(weather * weather_factor[i] <= var_names[f'v{i}'], name=f"weather_{var}_impact_{i}")
        
        model.setObjective(objective_expr, "maximize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'min_n': 75,
        'max_n': 125,
        'er_prob': 0.5,
        'edge_addition_prob': 0.3,
        'road_connectivity_prob': 0.2,
        'num_disaster_types': 3,
        'num_weather_types': 2,
        'alpha_impact': 2.0,
        'beta_impact': 1.0,
        'weather_mean': 0.0,
        'weather_std': 1.0,
    }

    maxsat = MaxSatisfiability(parameters, seed=seed)
    instance = maxsat.generate_instances()
    solve_status, solve_time = maxsat.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")