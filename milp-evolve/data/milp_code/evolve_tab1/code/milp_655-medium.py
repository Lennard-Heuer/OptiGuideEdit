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
############# Helper function #############

class IndependentSet:
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

        cliques = graph.efficient_greedy_clique_partition()
        inequalities = set(graph.edges)
        for clique in cliques:
            clique = tuple(sorted(clique))
            for edge in combinations(clique, 2):
                inequalities.remove(edge)
            if len(clique) > 1:
                inequalities.add(clique)

        # Allocate nurse availability
        nurse_availability = {node: np.random.randint(1, 40) for node in graph.nodes}

        # Put trivial inequalities for nodes that didn't appear
        # in the constraints, otherwise SCIP will complain
        used_nodes = set()
        for group in inequalities:
            used_nodes.update(group)
        for node in range(10):
            if node not in used_nodes:
                inequalities.add((node,))

        res = {'graph': graph,
               'inequalities': inequalities,
               'nurse_availability': nurse_availability}
        
        # New instance data
        partial_budgets = {node: np.random.uniform(1, nurse_availability[node]) for node in graph.nodes}

        res.update({'partial_budgets': partial_budgets})
        ### new instance data code ends here
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        inequalities = instance['inequalities']
        nurse_availability = instance['nurse_availability']
        partial_budgets = instance['partial_budgets']
        
        model = Model("IndependentSet")
        var_names = {}
        conv_hull_aux_vars = {}

        for node in graph.nodes:
            var_names[node] = model.addVar(vtype="B", name=f"x_{node}")
            conv_hull_aux_vars[node] = model.addVar(vtype="C", lb=0, ub=1, name=f"y_{node}")

        for count, group in enumerate(inequalities):
            model.addCons(quicksum(var_names[node] for node in group) <= 1, name=f"clique_{count}")

        # Convex Hull Constraints (making problem more complex)
        for node in graph.nodes:
            model.addCons(var_names[node] <= conv_hull_aux_vars[node], name=f"convex_hull_constraint1_{node}")
            model.addCons(conv_hull_aux_vars[node] <= nurse_availability[node], name=f"convex_hull_constraint2_{node}")

        objective_expr = quicksum(var_names[node] for node in graph.nodes)
        
        investment_limit = self.budget_limit

        # Nurse availability constraints
        for node in graph.nodes:
            model.addCons(var_names[node] <= nurse_availability[node], name=f"nurse_availability_{node}")

        # Budget constraint
        total_cost = quicksum(conv_hull_aux_vars[node] * partial_budgets[node] for node in graph.nodes)
        model.addCons(total_cost <= investment_limit, name="budget_limit")
        
        # New Bid Variables and Constraints (Placeholder for increment)
        bids = {i: model.addVar(vtype="B", name=f"bid_{i}") for i in range(len(graph.nodes))}
        for i in range(len(graph.nodes)):
            model.addCons(bids[i] + var_names[i] <= 1, name=f"bid_limit_{i}")
        
        model.setObjective(objective_expr, "maximize")
        
        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 750,
        'edge_probability': 0.48,
        'affinity': 4,
        'graph_type': 'barabasi_albert',
        'budget_limit': 10000,
    }
    ### new parameter code ends here
    independent_set_problem = IndependentSet(parameters, seed=seed)
    instance = independent_set_problem.generate_instance()
    solve_status, solve_time = independent_set_problem.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")