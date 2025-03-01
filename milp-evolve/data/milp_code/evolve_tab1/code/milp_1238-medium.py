import random
import time
import scipy
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum

class SetCoverWithSimplifiedUtility:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_instance(self):
        # Set Cover data generation
        nnzrs = int(self.n_rows * self.n_cols * self.density)

        indices = np.random.choice(self.n_cols, size=nnzrs)
        indices[:2 * self.n_cols] = np.repeat(np.arange(self.n_cols), 2)
        _, col_nrows = np.unique(indices, return_counts=True)

        indices[:self.n_rows] = np.random.permutation(self.n_rows)
        i = 0
        indptr = [0]
        for n in col_nrows:
            if i >= self.n_rows:
                indices[i:i+n] = np.random.choice(self.n_rows, size=n, replace=False)
            elif i + n > self.n_rows:
                remaining_rows = np.setdiff1d(np.arange(self.n_rows), indices[i:self.n_rows], assume_unique=True)
                indices[self.n_rows:i+n] = np.random.choice(remaining_rows, size=i+n-self.n_rows, replace=False)
            i += n
            indptr.append(i)

        c = np.random.randint(self.max_coef, size=self.n_cols) + 1
        A = scipy.sparse.csc_matrix(
                (np.ones(len(indices), dtype=int), indices, indptr),
                shape=(self.n_rows, self.n_cols)).tocsr()
        indices_csr = A.indices
        indptr_csr = A.indptr

        # Additional Data for Utility Constraints from GISP
        G = self.generate_random_graph()
        self.generate_revenues_costs(G)
        zone_limits = self.generate_zone_data(G)
        air_quality_limits = self.generate_air_quality_limits(G)

        return { 'c': c, 'indptr_csr': indptr_csr, 'indices_csr': indices_csr,
                 'G': G, 'zone_limits': zone_limits, 'air_quality_limits': air_quality_limits }

    def generate_random_graph(self):
        n_nodes = np.random.randint(self.min_n, self.max_n)
        G = nx.barabasi_albert_graph(n=n_nodes, m=self.ba_m, seed=self.seed)
        return G

    def generate_revenues_costs(self, G):
        for node in G.nodes:
            G.nodes[node]['revenue'] = np.random.randint(1, 100)

    def generate_zone_data(self, G):
        return {node: np.random.randint(self.min_zone_limit, self.max_zone_limit) for node in G.nodes}

    def generate_air_quality_limits(self, G):
        return {node: np.random.randint(self.min_air_quality, self.max_air_quality) for node in G.nodes}

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        c = instance['c']
        indptr_csr = instance['indptr_csr']
        indices_csr = instance['indices_csr']
        G = instance['G']
        zone_limits = instance['zone_limits']
        air_quality_limits = instance['air_quality_limits']

        model = Model("SetCoverWithSimplifiedUtility")
        var_names = {}
        node_vars = {node: model.addVar(vtype="B", name=f"x_{node}") for node in G.nodes}

        # SCP Variables and Objective
        for j in range(self.n_cols):
            var_names[j] = model.addVar(vtype="B", name=f"x_scp_{j}", obj=c[j])

        # Add coverage constraints for SCP
        for row in range(self.n_rows):
            cols = indices_csr[indptr_csr[row]:indptr_csr[row + 1]]
            model.addCons(quicksum(var_names[j] for j in cols) >= 1, f"c_{row}")

        # Utility Variables and Objective
        production_yield = {node: model.addVar(vtype="C", name=f"Y_{node}", lb=0) for node in G.nodes}

        utility_expr = quicksum(G.nodes[node]['revenue'] * node_vars[node] for node in G.nodes)

        # Constraints for Utility
        for node in G.nodes:
            model.addCons(production_yield[node] <= zone_limits[node], name=f"Zone_Limit_{node}")

        for node in G.nodes:
            neighbors = list(G.neighbors(node))
            model.addCons(quicksum(production_yield[neighbor] for neighbor in neighbors) <= air_quality_limits[node], name=f"Air_Quality_{node}")

        # Combined Objective
        objective_expr = quicksum(var_names[j] * c[j] for j in range(self.n_cols)) + utility_expr

        model.setObjective(objective_expr, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_rows': 750,
        'n_cols': 3000,
        'density': 0.1,
        'max_coef': 100,
        'min_n': 9,
        'max_n': 876,
        'ba_m': 150,
        'min_zone_limit': 2250,
        'max_zone_limit': 3000,
        'min_air_quality': 112,
        'max_air_quality': 700,
    }

    set_cover_with_simplified_utility = SetCoverWithSimplifiedUtility(parameters, seed=seed)
    instance = set_cover_with_simplified_utility.generate_instance()
    solve_status, solve_time = set_cover_with_simplified_utility.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")