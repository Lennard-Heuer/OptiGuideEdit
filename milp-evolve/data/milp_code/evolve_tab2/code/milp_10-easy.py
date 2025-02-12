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
############# Helper function #############

class GraphColoring:
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

        res = {'graph': graph}
        # New instance data for network flow
        edge_capacities = {edge: random.randint(1, 5) for edge in graph.edges}  # Random capacities for flow
        res['edge_capacities'] = edge_capacities
        # Define a source and a sink, e.g., first and last nodes
        res['source_node'] = 0
        res['sink_node'] = self.n_nodes - 1
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        edge_capacities = instance['edge_capacities']
        source_node = instance['source_node']
        sink_node = instance['sink_node']

        model = Model("GraphColoring")
        max_colors = self.max_colors
        var_names = {}
        flow_vars = {}

        # Variables: x[i, c] = 1 if node i is colored with color c, 0 otherwise
        for node in graph.nodes:
            for color in range(max_colors):
                var_names[(node, color)] = model.addVar(vtype="B", name=f"x_{node}_{color}")

        # Constraint: each node must have exactly one color
        for node in graph.nodes:
            model.addCons(quicksum(var_names[(node, color)] for color in range(max_colors)) == 1)

        # Constraint: adjacent nodes must have different colors
        for edge in graph.edges:
            node_u, node_v = edge
            if node_u < node_v:
                for color in range(max_colors):
                    model.addCons(var_names[(node_u, color)] + var_names[(node_v, color)] <= 1)

        # Objective: minimize the number of colors used
        color_used = [model.addVar(vtype="B", name=f"color_used_{color}") for color in range(max_colors)]
        for node in graph.nodes:
            for color in range(max_colors):
                model.addCons(var_names[(node, color)] <= color_used[color])
        
        # New flow variables and constraints
        for edge in graph.edges:
            node_u, node_v = edge
            flow_vars[(node_u, node_v)] = model.addVar(vtype="C", name=f"flow_{node_u}_{node_v}", lb=0, ub=edge_capacities[edge])

        # Flow conservation constraints
        for node in graph.nodes:
            if node == source_node or node == sink_node:
                continue
            model.addCons(
                quicksum(flow_vars.get((pred, node), 0) for pred in graph.neighbors[node]) ==
                quicksum(flow_vars.get((node, succ), 0) for succ in graph.neighbors[node]))

        # Ensure flow initiation at the source and absorption at the sink
        model.addCons(quicksum(flow_vars.get((source_node, succ), 0) for succ in graph.neighbors[source_node]) == max_colors)
        model.addCons(quicksum(flow_vars.get((pred, sink_node), 0) for pred in graph.neighbors[sink_node]) == max_colors)

        objective_expr = quicksum(color_used)
        model.setObjective(objective_expr, "minimize")
        
        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time


if __name__ == '__main__':
    seed = 42

    parameters = {
        'n_nodes': 500,
        'edge_probability': 0.52,
        'affinity': 4,
        'graph_type': 'barabasi_albert',
        'max_colors': 10,
    }

    graph_coloring_problem = GraphColoring(parameters, seed=seed)
    instance = graph_coloring_problem.generate_instance()
    solve_status, solve_time = graph_coloring_problem.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")