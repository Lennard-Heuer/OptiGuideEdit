import random
import time
import numpy as np
import networkx as nx
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
                # Can you add it to the clique, and maintain cliqueness?
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
            # first node is connected to all previous ones (star-shape)
            if new_node == affinity:
                neighborhood = np.arange(new_node)
            # remaining nodes are picked stochastically
            else:
                neighbor_prob = degrees[:new_node] / (2*len(edges))
                neighborhood = np.random.choice(new_node, affinity, replace=False, p=neighbor_prob)
            for node in neighborhood:
                edges.add((node, new_node))
                degrees[node] += 1
                degrees[new_node] += 1
                neighbors[node].add(new_node)
                neighbors[new_node].add(node)

        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph

    @staticmethod
    def watts_strogatz(number_of_nodes, k, p):
        """
        Generate a Watts-Strogatz small-world random graph.
        """
        graph_nx = nx.watts_strogatz_graph(number_of_nodes, k, p)
        edges = set(graph_nx.edges)
        degrees = np.array([deg for _, deg in graph_nx.degree])
        neighbors = {node: set(graph_nx.neighbors(node)) for node in graph_nx.nodes}
        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph

############# Helper function #############

class HierarchicalCommunicationNetwork:
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
        elif self.graph_type == 'watts_strogatz':
            graph = Graph.watts_strogatz(self.n_nodes, self.k, self.rewiring_prob)
        else:
            raise ValueError("Unsupported graph type.")
        return graph

    def generate_instance(self):
        graph = self.generate_graph()

        cliques = graph.efficient_greedy_clique_partition()
        dependencies = set(graph.edges)
        importances = np.random.randint(1, 10, size=graph.number_of_nodes)
        capacities = np.random.randint(10, 20, size=graph.number_of_nodes)

        for clique in cliques:
            clique = tuple(sorted(clique))
            for edge in combinations(clique, 2):
                dependencies.remove(edge)
            if len(clique) > 1:
                dependencies.add(clique)

        used_nodes = set()
        for group in dependencies:
            used_nodes.update(group)
        for node in range(10):
            if node not in used_nodes:
                dependencies.add((node,))

        res = {
            'graph': graph,
            'importances': importances,
            'capacities': capacities,
            'dependencies': dependencies,
            'central_nodes': random.sample(range(graph.number_of_nodes), k=10)
        }
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        dependencies = instance['dependencies']
        importances = instance['importances']
        capacities = instance['capacities']
        central_nodes = instance['central_nodes']
        
        model = Model("HierarchicalCommunicationNetwork")
        var_names = {}

        for node in graph.nodes:
            var_names[node] = model.addVar(vtype="B", name=f"x_{node}")

        for count, group in enumerate(dependencies):
            model.addCons(quicksum(var_names[node] for node in group) <= 1, name=f"cross_dependency_{count}")

        for i in range(len(capacities)):
            model.addCons(quicksum(importances[node] * var_names[node] for node in range(i, len(var_names), len(capacities))) <= capacities[i], name=f"hierarchical_allocation_{i}")

        for node in central_nodes:
            model.addCons(quicksum(var_names[node] for node in graph.neighbors[node]) >= 1, name=f"central_node_{node}")

        objective_expr = quicksum(var_names[node] * importances[node] for node in graph.nodes)
        model.setObjective(objective_expr, "maximize")
        
        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 375,
        'edge_probability': 0.45,
        'affinity': 1800,
        'k': 75,
        'rewiring_prob': 0.1,
        'graph_type': 'watts_strogatz',
    }

    hierarchical_network_problem = HierarchicalCommunicationNetwork(parameters, seed=seed)
    instance = hierarchical_network_problem.generate_instance()
    solve_status, solve_time = hierarchical_network_problem.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")