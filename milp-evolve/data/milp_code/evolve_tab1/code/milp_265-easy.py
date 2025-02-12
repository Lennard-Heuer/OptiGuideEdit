import random
import time
import numpy as np
from itertools import combinations
from pyscipopt import Model, quicksum

############# Helper function #############
class Graph:
    """
    Helper function: Container for a graph.
    """
    def __init__(self, number_of_nodes, edges, degrees, neighbors):
        self.number_of_nodes = number_of_nodes
        self.nodes = np.arange(number_of_nodes)
        self.edges = edges
        self.degrees = degrees
        self.neighbors = neighbors

    def efficient_greedy_clique_partition(self):
        """
        Partition the graph into cliques using an efficient greedy algorithm.
        """
        cliques = []
        leftover_nodes = (-self.degrees).argsort().tolist()

        while leftover_nodes:
            clique_center, leftover_nodes = leftover_nodes[0], leftover_nodes[1:]
            clique = {clique_center}
            neighbors = self.neighbors[clique_center].intersection(leftover_nodes)
            densest_neighbors = sorted(neighbors, key=lambda x: -self.degrees[x])
            for neighbor in densest_neighbors:
                if all([neighbor in self.neighbors[clique_node] for clique_node in clique]):
                    clique.add(neighbor)
            cliques.append(clique)
            leftover_nodes = [node for node in leftover_nodes if node not in clique]

        return cliques

    @staticmethod
    def erdos_renyi(number_of_nodes, edge_probability):
        """
        Generate an Erdös-Rényi random graph with a given edge probability.
        """
        edges = set()
        degrees = np.zeros(number_of_nodes, dtype=int)
        neighbors = {node: set() for node in range(number_of_nodes)}
        for edge in combinations(np.arange(number_of_nodes), 2):
            if np.random.uniform() < edge_probability:
                edges.add(edge)
                degrees[edge[0]] += 1
                degrees[edge[1]] += 1
                neighbors[edge[0]].add(edge[1])
                neighbors[edge[1]].add(edge[0])
        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph

    @staticmethod
    def barabasi_albert(number_of_nodes, affinity):
        """
        Generate a Barabási-Albert random graph with a given edge probability.
        """
        assert affinity >= 1 and affinity < number_of_nodes

        edges = set()
        degrees = np.zeros(number_of_nodes, dtype=int)
        neighbors = {node: set() for node in range(number_of_nodes)}
        for new_node in range(affinity, number_of_nodes):
            if new_node == affinity:
                neighborhood = np.arange(new_node)
            else:
                neighbor_prob = degrees[:new_node] / (2 * len(edges))
                neighborhood = np.random.choice(new_node, affinity, replace=False, p=neighbor_prob)
            for node in neighborhood:
                edges.add((node, new_node))
                degrees[node] += 1
                degrees[new_node] += 1
                neighbors[node].add(new_node)
                neighbors[new_node].add(node)

        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph
############# Helper function #############

class RobustIndependentSet:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# data generation #################
    def generate_graph(self):
        if self.graph_type == 'erdos_renyi':
            graph = Graph.erdos_renyi(self.n_nodes, self.edge_probability)
        elif self.graph_type == 'barabasi_albert':
            graph = Graph.barabasi_albert(self.n_nodes, self.affinity)
        else:
            raise ValueError("Unsupported graph type.")
        return graph

    def generate_instance(self):
        graph = self.generate_graph()
        
        # Generate node existence probabilities
        node_existence_prob = np.random.uniform(0.8, 1, self.n_nodes)
        
        # Generate node weights with deviations
        node_weights = np.random.randint(1, self.max_weight, self.n_nodes)
        node_weight_deviations = np.random.rand(self.n_nodes) * self.weight_deviation_factor
        knapsack_capacity = np.random.randint(self.min_capacity, self.max_capacity)
        
        cliques = graph.efficient_greedy_clique_partition()
        inequalities = set(graph.edges)
        for clique in cliques:
            clique = tuple(sorted(clique))
            for edge in combinations(clique, 2):
                inequalities.remove(edge)
            if len(clique) > 1:
                inequalities.add(clique)
        
        # Additional supply chain parameters
        supply_nodes = self.supply_nodes
        demand_nodes = self.demand_nodes
        arcs = [(i, j) for i in range(supply_nodes) for j in range(demand_nodes)]
        supply_capacities = np.random.randint(50, 150, size=supply_nodes)
        demand = np.random.randint(30, 100, size=demand_nodes)
        transportation_costs = np.random.randint(1, 20, size=(supply_nodes, demand_nodes))
        
        res = {'graph': graph,
               'inequalities': inequalities,
               'node_existence_prob': node_existence_prob,
               'node_weights': node_weights,
               'node_weight_deviations': node_weight_deviations,
               'knapsack_capacity': knapsack_capacity,
               'supply_capacities': supply_capacities,
               'demand': demand,
               'transportation_costs': transportation_costs,
               'arcs': arcs}
        
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        inequalities = instance['inequalities']
        node_existence_prob = instance['node_existence_prob']
        node_weights = instance['node_weights']
        node_weight_deviations = instance['node_weight_deviations']
        knapsack_capacity = instance['knapsack_capacity']

        supply_capacities = instance['supply_capacities']
        demand = instance['demand']
        transportation_costs = instance['transportation_costs']
        arcs = instance['arcs']
        supply_nodes = self.supply_nodes
        demand_nodes = self.demand_nodes

        model = Model("RobustIndependentSet")
        var_names = {}

        for node in graph.nodes:
            var_names[node] = model.addVar(vtype="B", name=f"x_{node}")

        for count, group in enumerate(inequalities):
            if len(group) > 1:
                model.addCons(quicksum(var_names[node] for node in group) <= 1, name=f"clique_{count}")

        # Define the robust knapsack constraint
        node_weight_constraints = quicksum((node_weights[node] + node_weight_deviations[node]) * var_names[node] for node in graph.nodes)
        model.addCons(node_weight_constraints <= knapsack_capacity, name="robust_knapsack")

        # Define the objective to include piecewise linear costs
        objective_expr = quicksum(node_existence_prob[node] * var_names[node] for node in graph.nodes)
        
        ### Add Constraints, Variables, or Objectives ###
        # Define flow variables for supply chain part
        flow_vars = {}
        for i, j in arcs:
            flow_vars[(i, j)] = model.addVar(vtype="C", name=f"flow_{i}_{j}")

        # Supply capacity constraints
        for i in range(supply_nodes):
            model.addCons(quicksum(flow_vars[(i, j)] for j in range(demand_nodes)) <= supply_capacities[i], f"supply_capacity_{i}")

        # Demand satisfaction constraints
        for j in range(demand_nodes):
            model.addCons(quicksum(flow_vars[(i, j)] for i in range(supply_nodes)) >= demand[j], f"demand_{j}")

        # Transportation costs in the objective
        transportation_cost_expr = quicksum(flow_vars[(i, j)] * transportation_costs[i, j] for (i, j) in arcs)
        objective_expr += transportation_cost_expr
        
        model.setObjective(objective_expr, "maximize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time


if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 421,
        'edge_probability': 0.59,
        'affinity': 27,
        'graph_type': 'barabasi_albert',
        'max_weight': 2025,
        'min_capacity': 10000,
        'max_capacity': 15000,
        'weight_deviation_factor': 0.66,
        'supply_nodes': 50,
        'demand_nodes': 45,
    }

    robust_independent_set = RobustIndependentSet(parameters, seed=seed)
    instance = robust_independent_set.generate_instance()
    solve_status, solve_time = robust_independent_set.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")