import random
import time
import scipy
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum

class SimplifiedLogisticsOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_instance(self):
        nnzrs = int(self.n_rows * self.n_cols * self.density)

        # compute number of rows per column
        indices = np.random.choice(self.n_cols, size=nnzrs)  # random column indexes
        indices[:2 * self.n_cols] = np.repeat(np.arange(self.n_cols), 2)  # force at least 2 rows per col
        _, col_nrows = np.unique(indices, return_counts=True)

        # for each column, sample random rows
        indices[:self.n_rows] = np.random.permutation(self.n_rows) # force at least 1 column per row
        i = 0
        indptr = [0]
        for n in col_nrows:
            if i >= self.n_rows:
                indices[i:i + n] = np.random.choice(self.n_rows, size=n, replace=False)
            elif i + n > self.n_rows:
                remaining_rows = np.setdiff1d(np.arange(self.n_rows), indices[i:self.n_rows], assume_unique=True)
                indices[self.n_rows:i + n] = np.random.choice(remaining_rows, size=i + n - self.n_rows,
                                                              replace=False)
            i += n
            indptr.append(i)

        c = np.random.randint(self.max_coef, size=self.n_cols) + 1
        
        graph = nx.erdos_renyi_graph(self.n_cols, self.edge_prob, seed=self.seed)
        capacities = np.random.randint(1, self.max_capacity, size=len(graph.edges))
        flows = np.random.uniform(0, self.max_flow, size=len(graph.edges))
        
        source_node, sink_node = 0, self.n_cols - 1

        adj_list = {i: [] for i in range(self.n_cols)}
        for idx, (u, v) in enumerate(graph.edges):
            adj_list[u].append((v, flows[idx], capacities[idx]))
            adj_list[v].append((u, flows[idx], capacities[idx]))
        
        A = scipy.sparse.csc_matrix(
            (np.ones(len(indices), dtype=int), indices, indptr),
            shape=(self.n_rows, self.n_cols)).tocsr()
        indices_csr = A.indices
        indptr_csr = A.indptr

        res = {'c': c,
               'indptr_csr': indptr_csr,
               'indices_csr': indices_csr,
               'adj_list': adj_list,
               'source_node': source_node,
               'sink_node': sink_node}

        depot_capacity = np.random.randint(1, self.max_depot_capacity, size=self.n_depots)
        depot_zones = {i: np.random.choice(range(self.n_cols), size=self.n_depots_in_zone, replace=False) for i in
                         range(self.n_depots)}
        
        demand = np.random.uniform(1, self.max_demand, size=self.n_cols)

        res.update({'depot_capacity': depot_capacity, 
                    'depot_zones': depot_zones,
                    'demand': demand})

        # New instance generation for Big M values
        res['big_M'] = np.random.randint(1000, 5000, size=len(graph.edges))

        return res

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        c = instance['c']
        indptr_csr = instance['indptr_csr']
        indices_csr = instance['indices_csr']
        adj_list = instance['adj_list']
        source_node = instance['source_node']
        sink_node = instance['sink_node']
        depot_capacity = instance['depot_capacity']
        depot_zones = instance['depot_zones']
        demand = instance['demand']
        big_M = instance['big_M']

        model = Model("SimplifiedLogisticsOptimization")
        var_names = {}

        for j in range(self.n_cols):
            var_names[j] = model.addVar(vtype="B", name=f"x_{j}", obj=c[j])
          
        flow_vars = {}
        usage_vars = {}
        for u in adj_list:
            for v, flow, capacity in adj_list[u]:
                flow_vars[(u, v)] = model.addVar(vtype='C', lb=0, ub=capacity, name=f"f_{u}_{v}")
                usage_vars[(u, v)] = model.addVar(vtype="B", name=f"u_{u}_{v}")

        for row in range(self.n_rows):
            cols = indices_csr[indptr_csr[row]:indptr_csr[row + 1]]
            model.addCons(quicksum(var_names[j] for j in cols) >= 1, f"c_{row}")

        for node in adj_list:
            inflow = quicksum(flow_vars[(u, node)] for u, _, _ in adj_list[node] if (u, node) in flow_vars)
            outflow = quicksum(flow_vars[(node, v)] for v, _, _ in adj_list[node] if (node, v) in flow_vars)
            model.addCons(inflow - outflow == 0, f"flow_balance_{node}")

        depot_vars = {}
        for zone, cols in depot_zones.items():
            for col in cols:
                depot_vars[col] = model.addVar(vtype="B", name=f"d_{col}")
                model.addCons(var_names[col] <= depot_vars[col], f"allocate_{col}")

            model.addCons(quicksum(depot_vars[col] for col in cols) <= depot_capacity[zone], f"depot_limit_{zone}")

        for (u, v), M in zip(flow_vars.keys(), big_M):
            model.addCons(flow_vars[(u, v)] <= M * usage_vars[(u, v)], f"big_M_{u}_{v}")
            model.addCons(usage_vars[(u, v)] <= var_names[u], f"usage_link_{u}_{v}_u")

        cost_term = quicksum(var_names[j] * c[j] for j in range(self.n_cols))
        flow_term = quicksum(flow_vars[(u, v)] for u, v in flow_vars)
        depot_penalty_term = quicksum(depot_vars[col] for col in depot_vars)

        objective_expr = cost_term - self.flow_weight * flow_term + self.depot_penalty_weight * depot_penalty_term

        model.setObjective(objective_expr, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_rows': 3000,
        'n_cols': 210,
        'density': 0.17,
        'max_coef': 168,
        'edge_prob': 0.59,
        'max_capacity': 60,
        'max_flow': 875,
        'flow_weight': 0.45,
        'n_depots': 15,
        'n_depots_in_zone': 33,
        'max_depot_capacity': 105,
        'depot_penalty_weight': 0.38,
        'max_demand': 112,
    }

    simplified_logistics_optimization = SimplifiedLogisticsOptimization(parameters, seed=seed)
    instance = simplified_logistics_optimization.generate_instance()
    solve_status, solve_time = simplified_logistics_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")