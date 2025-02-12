import random
import time
import numpy as np
import networkx as nx
from itertools import combinations
from pyscipopt import Model, quicksum

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
        """ Generate an Erdös-Rényi random graph with a given edge probability. """
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
    def barabasi_albert(number_of_nodes, edges_to_attach):
        """ Generate a Barabási-Albert random graph. """
        edges = set()
        neighbors = {node: set() for node in range(number_of_nodes)}
        G = nx.barabasi_albert_graph(number_of_nodes, edges_to_attach)
        degrees = np.zeros(number_of_nodes, dtype=int)
        for edge in G.edges:
            edges.add(edge)
            degrees[edge[0]] += 1
            degrees[edge[1]] += 1
            neighbors[edge[0]].add(edge[1])
            neighbors[edge[1]].add(edge[0])
        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph

class HospitalZoningOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_graph(self):
        if self.graph_type == 'erdos_renyi':
            return Graph.erdos_renyi(self.n_nodes, self.edge_probability)
        elif self.graph_type == 'barabasi_albert':
            return Graph.barabasi_albert(self.n_nodes, self.edges_to_attach)
        else:
            raise ValueError("Unsupported graph type.")

    def generate_instance(self):
        graph = self.generate_graph()
        demands = np.random.randint(1, 100, size=graph.number_of_nodes)
        populations = np.random.randint(500, 5000, size=graph.number_of_nodes)
        metropolitan_zone = np.random.choice([0, 1], size=graph.number_of_nodes, p=[0.7, 0.3])
        distances = np.random.randint(1, 100, size=(graph.number_of_nodes, graph.number_of_nodes))
        
        # Hospital parameters
        hospital_costs = np.random.randint(100, 300, size=graph.number_of_nodes)
        ambulance_costs = np.random.rand(graph.number_of_nodes, graph.number_of_nodes) * 50

        res = {
            'graph': graph,
            'demands': demands,
            'populations': populations,
            'metropolitan_zone': metropolitan_zone,
            'distances': distances,
            'hospital_costs': hospital_costs,
            'ambulance_costs': ambulance_costs
        }
        
        upper_capacity_limits = np.random.randint(100, 500, size=graph.number_of_nodes)
        max_budget = np.random.randint(1000, 5000)

        # New Data for Increased Complexity
        critical_care_demand = np.random.randint(1, 100, size=graph.number_of_nodes)
        network_capacity = np.random.randint(100, 500, size=graph.number_of_nodes)
        service_hours = np.random.randint(1, 10, size=(graph.number_of_nodes, graph.number_of_nodes))

        res.update({
            'upper_capacity_limits': upper_capacity_limits,
            'max_budget': max_budget,
            'critical_care_demand': critical_care_demand,
            'network_capacity': network_capacity,
            'service_hours': service_hours
        })
        return res

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        graph = instance['graph']
        demands = instance['demands']
        populations = instance['populations']
        metropolitan_zone = instance['metropolitan_zone']
        distances = instance['distances']
        hospital_costs = instance['hospital_costs']
        ambulance_costs = instance['ambulance_costs']
        upper_capacity_limits = instance['upper_capacity_limits']
        max_budget = instance['max_budget']
        critical_care_demand = instance['critical_care_demand']
        network_capacity = instance['network_capacity']
        service_hours = instance['service_hours']

        model = Model("HospitalZoningOptimization")

        # Add variables
        hospital_vars = {node: model.addVar(vtype="B", name=f"CitySelection_{node}") for node in graph.nodes}
        ambulance_vars = {(i, j): model.addVar(vtype="B", name=f"HospitalRouting_{i}_{j}") for i in graph.nodes for j in graph.nodes}

        # New service time variables
        ServiceTime_vars = {node: model.addVar(vtype="C", name=f"ServiceTime_{node}") for node in graph.nodes}

        # Zoning constraints: Metropolitan zone must have at least one hospital
        for zone in graph.nodes:
            if metropolitan_zone[zone] == 1:
                model.addCons(quicksum(hospital_vars[node] for node in graph.nodes) >= 1, name=f"MetropolitanZone_{zone}")

        # Demand satisfaction constraints
        for zone in graph.nodes:
            model.addCons(quicksum(ambulance_vars[zone, hospital] for hospital in graph.nodes) == 1, name=f"Demand_{zone}")

        # Routing from open hospitals
        for i in graph.nodes:
            for j in graph.nodes:
                model.addCons(ambulance_vars[i,j] <= hospital_vars[j], name=f"Service_{i}_{j}")

        # Budget constraints
        total_cost = quicksum(hospital_vars[node] * hospital_costs[node] for node in graph.nodes) + \
                     quicksum(ambulance_vars[i, j] * ambulance_costs[i, j] for i in graph.nodes for j in graph.nodes)
        model.addCons(total_cost <= max_budget, name="Budget")

        # Capacity constraints
        for node in graph.nodes:
            model.addCons(quicksum(ambulance_vars[i, node] for i in graph.nodes) <= upper_capacity_limits[node], name=f"Capacity_{node}")

        # Network Capacity Constraints for healthcare centers
        for center in graph.nodes:
            model.addCons(quicksum(critical_care_demand[node] * ambulance_vars[node, center] for node in graph.nodes) <= network_capacity[center], name=f"NetworkCapacity_{center}")

        # Service time constraints
        for node in graph.nodes:
            model.addCons(ServiceTime_vars[node] >= 0, name=f'ServiceMinTime_{node}')
            model.addCons(ServiceTime_vars[node] <= service_hours.max(), name=f'ServiceMaxTime_{node}')

        model.setObjective(total_cost, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 55,
        'edge_probability': 0.24,
        'graph_type': 'erdos_renyi',
        'edges_to_attach': 0,
    }
    hospital_zoning_optimization = HospitalZoningOptimization(parameters, seed=seed)
    instance = hospital_zoning_optimization.generate_instance()
    solve_status, solve_time = hospital_zoning_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")