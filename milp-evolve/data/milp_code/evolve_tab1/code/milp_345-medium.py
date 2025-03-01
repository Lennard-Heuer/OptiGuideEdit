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

class CourierRouteOptimization:
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
        point_service_prob = np.random.uniform(0.8, 1, self.n_nodes)
        
        # Generate handling capacities with deviations
        handling_capacities = np.random.randint(1, self.max_capacity, self.n_nodes)
        handling_deviations = np.random.rand(self.n_nodes) * self.capacity_deviation_factor
        delivery_volume = np.random.randint(self.min_volume, self.max_volume)
        
        neighborhoods = graph.efficient_greedy_clique_partition()
        neighborhood_constraints = set(graph.edges)
        for neighborhood in neighborhoods:
            neighborhood = tuple(sorted(neighborhood))
            for edge in combinations(neighborhood, 2):
                neighborhood_constraints.remove(edge)
            if len(neighborhood) > 1:
                neighborhood_constraints.add(neighborhood)
        
        # Additional courier route parameters
        supply_points = self.supply_points
        demand_points = self.demand_points
        routes = [(i, j) for i in range(supply_points) for j in range(demand_points)]
        courier_availability = np.random.randint(50, 150, size=supply_points)
        delivery_requirements = np.random.randint(30, 100, size=demand_points)
        travel_times = np.random.randint(1, 20, size=(supply_points, demand_points))

        res = {'graph': graph,
               'neighborhood_constraints': neighborhood_constraints,
               'point_service_prob': point_service_prob,
               'handling_capacities': handling_capacities,
               'handling_deviations': handling_deviations,
               'delivery_volume': delivery_volume,
               'courier_availability': courier_availability,
               'delivery_requirements': delivery_requirements,
               'travel_times': travel_times,
               'routes': routes}
        
        # New semi-continuous variables data
        min_flow_threshold = np.random.randint(5, 15, size=(supply_points, demand_points))
        res['min_flow_threshold'] = min_flow_threshold

        # Introduce flow balance data at intermediate nodes
        intermediate_flow_balances = np.random.randint(10, 50, size=supply_points)
        res['intermediate_flow_balances'] = intermediate_flow_balances
        
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        graph = instance['graph']
        neighborhood_constraints = instance['neighborhood_constraints']
        point_service_prob = instance['point_service_prob']
        handling_capacities = instance['handling_capacities']
        handling_deviations = instance['handling_deviations']
        delivery_volume = instance['delivery_volume']

        courier_availability = instance['courier_availability']
        delivery_requirements = instance['delivery_requirements']
        travel_times = instance['travel_times']
        routes = instance['routes']
        supply_points = self.supply_points
        demand_points = self.demand_points
        min_flow_threshold = instance['min_flow_threshold']
        intermediate_flow_balances = instance['intermediate_flow_balances']

        model = Model("CourierRouteOptimization")
        assign_vars = {}
        flow_vars = {}
        flow_active_vars = {}

        for node in graph.nodes:
            assign_vars[node] = model.addVar(vtype="B", name=f"assign_{node}")

        for count, group in enumerate(neighborhood_constraints):
            if len(group) > 1:
                model.addCons(quicksum(assign_vars[node] for node in group) <= 1, name=f"NeighborhoodConstraint_{count}")

        # Define the handling capacity constraint
        handling_constraints = quicksum((handling_capacities[node] + handling_deviations[node]) * assign_vars[node] for node in graph.nodes)
        model.addCons(handling_constraints <= delivery_volume, name="HandlingCapacity")

        # Define the objective to maximize the point service probability
        objective_expr = quicksum(point_service_prob[node] * assign_vars[node] for node in graph.nodes)

        # Define flow variables for courier routes and activation variables
        for i, j in routes:
            flow_vars[(i, j)] = model.addVar(vtype="C", name=f"flow_{i}_{j}")
            flow_active_vars[(i, j)] = model.addVar(vtype="B", name=f"flow_active_{i}_{j}")

        # Courier availability constraints
        for i in range(supply_points):
            model.addCons(quicksum(flow_vars[(i, j)] for j in range(demand_points)) <= courier_availability[i], f"CourierCapacity_{i}")

        # Delivery requirements constraints
        for j in range(demand_points):
            model.addCons(quicksum(flow_vars[(i, j)] for i in range(supply_points)) >= delivery_requirements[j], f"DeliveryRequirement_{j}")

        # Minimum flow threshold constraints
        for i, j in routes:
            model.addCons(flow_vars[(i, j)] >= min_flow_threshold[i, j] * flow_active_vars[(i, j)], name=f"MinFlow_{i}_{j}")

        # Travel times in the objective
        travel_time_expr = quicksum(flow_vars[(i, j)] * travel_times[i, j] for (i, j) in routes)
        objective_expr += travel_time_expr

        # Flow balance constraints at intermediate nodes for convex combination
        for i in range(supply_points):
            model.addCons(quicksum(flow_vars[(i, j)] for j in range(demand_points)) == intermediate_flow_balances[i], f"FlowBalance_{i}")

        model.setObjective(objective_expr, "maximize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time


if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 315,
        'edge_probability': 0.73,
        'affinity': 20,
        'graph_type': 'barabasi_albert',
        'max_capacity': 1138,
        'min_volume': 10000,
        'max_volume': 15000,
        'capacity_deviation_factor': 0.66,
        'supply_points': 1500,
        'demand_points': 112,
    }

    courier_route_optimization = CourierRouteOptimization(parameters, seed=seed)
    instance = courier_route_optimization.generate_instance()
    solve_status, solve_time = courier_route_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")