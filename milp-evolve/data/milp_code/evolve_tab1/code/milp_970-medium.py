import random
import time
import numpy as np
from scipy.stats import norm
from pyscipopt import Model, quicksum
import networkx as nx

class CombinedOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        if seed:
            random.seed(seed)
            np.random.seed(seed)

    def randint(self, size, interval):
        return np.random.randint(interval[0], interval[1], size)
    
    def gen_graph_data(self):
        G = nx.barabasi_albert_graph(self.n_paths, 3)
        for u, v, data in G.edges(data=True):
            data['weight'] = np.random.exponential(scale=2)  # generating diverse weight
        adjacency_matrix = nx.adjacency_matrix(G).toarray()
        return adjacency_matrix

    def generate_instance(self):
        packet_rates = self.randint(self.n_packets, self.packet_rate_interval)
        path_capacities = self.randint(self.n_paths, self.path_capacity_interval)
        connection_costs = self.randint(self.n_paths, self.connection_cost_interval)
        delay_dist_params = np.random.gamma(2.0, 2.0, (self.n_packets, self.n_paths))  # Diverse delay generation
        budget_limits = self.randint(self.n_paths, (1000, 2000))

        path_capacities = path_capacities * self.ratio * np.sum(packet_rates) / np.sum(path_capacities)
        path_capacities = np.round(path_capacities)

        packet_priorities = self.randint(self.n_packets, (0, 2))  # Binary {0,1} priority

        weights = self.randint(self.n_packets, (2, 300))
        profits = self.randint(self.n_packets, (2, 300)) + weights
        mutual_exclusivity_pairs = [(random.randint(0, self.n_packets - 1), random.randint(0, self.n_packets - 1)) for _ in range(self.number_of_exclusive_pairs)]
        bids = [(random.sample(range(self.n_packets), random.randint(1, self.max_bundle_size)), random.randint(self.min_profit_bid, self.max_profit_bid)) for _ in range(self.number_of_bids)]

        res = {
            'packet_rates': packet_rates,
            'path_capacities': path_capacities,
            'connection_costs': connection_costs,
            'delay_dist_params': delay_dist_params,
            'budget_limits': budget_limits,
            'packet_priorities': packet_priorities,
            'adjacency_matrix': self.gen_graph_data(),  # Graph-based data
            'weights': weights,
            'profits': profits,
            'mutual_exclusivity_pairs': mutual_exclusivity_pairs,
            'bids': bids
        }
        return res

    def solve(self, instance):
        # Instance data
        packet_rates = instance['packet_rates']
        path_capacities = instance['path_capacities']
        connection_costs = instance['connection_costs']
        delay_dist_params = instance['delay_dist_params']
        budget_limits = instance['budget_limits']
        packet_priorities = instance['packet_priorities']
        adjacency_matrix = instance['adjacency_matrix']
        weights = instance['weights']
        profits = instance['profits']
        mutual_exclusivity_pairs = instance['mutual_exclusivity_pairs']
        bids = instance['bids']

        n_packets = len(packet_rates)
        n_paths = len(path_capacities)

        model = Model("CombinedOptimization")

        # Decision variables
        activate_path = {j: model.addVar(vtype="B", name=f"Activate_{j}") for j in range(n_paths)}
        route_packet = {(i, j): model.addVar(vtype="B", name=f"Route_{i}_{j}") for i in range(n_packets) for j in range(n_paths)}
        total_cost = {j: model.addVar(vtype="C", name=f"TotalCost_{j}") for j in range(n_paths)}
        overload_penalty = {j: model.addVar(vtype="I", name=f"OverloadPenalty_{j}") for j in range(n_paths)}
        bundle_vars = {b_idx: model.addVar(vtype="B", name=f"bundle_bid_{b_idx}") for b_idx in range(len(bids))}

        # Objective: Minimize the weighted sum of total cost, delay, and overload penalties
        penalty_for_overloading = 300
        objective_expr = (quicksum(total_cost[j] for j in range(n_paths)) + 
                          penalty_for_overloading * quicksum(overload_penalty[j] for j in range(n_paths)) + 
                          quicksum(bids[b_idx][1] * bundle_vars[b_idx] for b_idx in range(len(bids))))
        
        model.setObjective(objective_expr, "minimize")

        # Constraints: each packet must be sent through exactly one path
        for i in range(n_packets):
            model.addCons(quicksum(route_packet[i, j] for j in range(n_paths)) == 1, f"Packet_Routing_{i}")
        
        # Constraints: path capacity limits must be respected
        for j in range(n_paths):
            model.addCons(quicksum(packet_rates[i] * route_packet[i, j] for i in range(n_packets)) <= path_capacities[j] * activate_path[j], f"Path_Capacity_{j}")

        # Constraints: budget limits per path
        for j in range(n_paths):
            model.addCons(total_cost[j] <= budget_limits[j], f"Budget_Limit_{j}")
        
        # Update total cost as a combination of connection cost and delay
        for j in range(n_paths):
            model.addCons(total_cost[j] == quicksum(delay_dist_params[i][j] * route_packet[i, j] for i in range(n_packets)) + connection_costs[j] * activate_path[j], f"Total_Cost_{j}")
        
        # Constraints: Penalty for overloading paths
        for j in range(n_paths):
            model.addCons(overload_penalty[j] >= quicksum(route_packet[i, j] * delay_dist_params[i][j] for i in range(n_packets)) - path_capacities[j] * activate_path[j], f"Overload_Penalty_{j}")

        # Constraints enforcing path adjacency (graph-based)
        for i in range(n_packets):
            for j in range(n_paths):
                for k in range(n_paths):
                    if adjacency_matrix[j][k] == 1:  # If j and k are connected
                        model.addCons(route_packet[i, j] + route_packet[i, k] <= 1, f"Adjacency_{i}_{j}_{k}")
        
        # Constraints: Mutual exclusivity of items
        for i1, i2 in mutual_exclusivity_pairs:
            for j in range(n_paths):
                model.addCons(route_packet[i1, j] + route_packet[i2, j] <= 1, f"MutualExclusivity_{i1}_{i2}_{j}")
                
        # Constraints: Bundle item inclusion
        for b_idx, (bundle, _) in enumerate(bids):
            for i in bundle:
                model.addCons(quicksum(route_packet[i, j] for j in range(n_paths)) >= bundle_vars[b_idx], f"Bundle_{b_idx}_{i}")

        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_packets': 262,
        'n_paths': 75,
        'packet_rate_interval': (98, 980),
        'path_capacity_interval': (900, 2700),
        'connection_cost_interval': (1200, 2400),
        'ratio': 2250.0,
        'number_of_exclusive_pairs': 370,
        'number_of_bids': 60,
        'max_bundle_size': 75,
        'min_profit_bid': 150,
        'max_profit_bid': 1800,
    }

    combined_optimization = CombinedOptimization(parameters, seed=seed)
    instance = combined_optimization.generate_instance()
    solve_status, solve_time = combined_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")