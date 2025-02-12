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

class ConvexHullPartition:
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

        # Generate capacities and transportation costs
        capacities = np.random.randint(1, 100, self.n_nodes)
        transportation_costs = np.random.uniform(0.1, 1.0, self.n_nodes)
        
        cliques = graph.efficient_greedy_clique_partition()
        inequalities = set(graph.edges)
        for clique in cliques:
            clique = tuple(sorted(clique))
            for edge in combinations(clique, 2):
                inequalities.remove(edge)
            if len(clique) > 1:
                inequalities.add(clique)

        res = {'graph': graph,
               'inequalities': inequalities,
               'node_existence_prob': node_existence_prob,
               'capacities': capacities,
               'transportation_costs': transportation_costs}

        res['clique_indices'] = {i: clique for i, clique in enumerate(cliques)}

        # Add new data for cluster pairs
        cluster_affiliations = {node: random.randint(0, self.n_clusters-1) for node in graph.nodes}
        res["cluster_affiliations"] = cluster_affiliations

        ### given instance data code ends here
        ### new instance data code ends here
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        inequalities = instance['inequalities']
        node_existence_prob = instance['node_existence_prob']
        capacities = instance['capacities']
        transportation_costs = instance['transportation_costs']
        clique_indices = instance['clique_indices']
        cluster_affiliations = instance["cluster_affiliations"]

        model = Model("ConvexHullPartition")
        var_names = {}
        lambda_vars = {}

        for node in graph.nodes:
            var_names[node] = model.addVar(vtype="B", name=f"x_{node}")

        for edge in graph.edges:
            u, v = edge
            model.addCons(var_names[u] + var_names[v] <= 1, name=f"edge_{u}_{v}")

        for count, group in enumerate(inequalities):
            if len(group) > 1:  # Consider only non-trivial cliques (more than one node)
                model.addCons(quicksum(var_names[node] for node in group) <= 1, name=f"clique_{count}")

        for k in range(self.n_clusters):
            lambda_vars[k] = model.addVar(vtype="B", name=f"lambda_{k}")
            for node in graph.nodes:
                if cluster_affiliations[node] == k:
                    model.addCons(var_names[node] <= lambda_vars[k], name=f"convex_{k}_{node}")

        objective_expr = quicksum(node_existence_prob[node] * var_names[node] - transportation_costs[node] for node in graph.nodes)

        for node in graph.nodes:
            model.addCons(quicksum(var_names[neighbor] for neighbor in graph.neighbors[node] if neighbor != node) <= capacities[node], name=f"capacity_{node}")

        ### given constraints and variables and objective code ends here
        ### new constraints and variables and objective code ends here
        model.setObjective(objective_expr, "maximize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time, model.getObjVal()

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 3000,
        'edge_probability': 0.8,
        'affinity': 4,
        'graph_type': 'barabasi_albert',
        'n_clusters': 70,
    }
    ### given parameter code ends here
    ### new parameter code ends here

    convex_hull_partition_problem = ConvexHullPartition(parameters, seed=seed)
    instance = convex_hull_partition_problem.generate_instance()
    solve_status, solve_time, objective_value = convex_hull_partition_problem.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")
    print(f"Objective Value: {objective_value:.2f}")