import random
import time
import numpy as np
import networkx as nx
from itertools import permutations
from pyscipopt import Model, quicksum

class Graph:
    """Helper function: Container for a graph."""
    def __init__(self, number_of_nodes, edges, degrees, neighbors):
        self.number_of_nodes = number_of_nodes
        self.nodes = np.arange(number_of_nodes)
        self.edges = edges
        self.degrees = degrees
        self.neighbors = neighbors

    @staticmethod
    def erdos_renyi(number_of_nodes, edge_probability):
        """Generate an Erdös-Rényi random graph with a given edge probability."""
        edges = set()
        degrees = np.zeros(number_of_nodes, dtype=int)
        neighbors = {node: set() for node in range(number_of_nodes)}
        for edge in permutations(np.arange(number_of_nodes), 2):
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
        """Generate a Barabási-Albert random graph."""
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

    @staticmethod
    def watts_strogatz(number_of_nodes, k, p):
        """Generate a Watts-Strogatz small-world graph."""
        edges = set()
        neighbors = {node: set() for node in range(number_of_nodes)}
        G = nx.watts_strogatz_graph(number_of_nodes, k, p)
        degrees = np.zeros(number_of_nodes, dtype=int)
        for edge in G.edges:
            edges.add(edge)
            degrees[edge[0]] += 1
            degrees[edge[1]] += 1
            neighbors[edge[0]].add(edge[1])
            neighbors[edge[1]].add(edge[0])
        graph = Graph(number_of_nodes, edges, degrees, neighbors)
        return graph

class WarehouseAllocationOptimization:
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
        elif self.graph_type == 'watts_strogatz':
            return Graph.watts_strogatz(self.n_nodes, self.k, self.rewiring_prob)
        else:
            raise ValueError("Unsupported graph type.")

    def generate_instance(self):
        graph = self.generate_graph()
        demands = np.random.randint(1, 100, size=graph.number_of_nodes)
        populations = np.random.randint(500, 5000, size=graph.number_of_nodes)
        distances = np.random.randint(1, 100, size=(graph.number_of_nodes, graph.number_of_nodes))

        # Warehouse parameters
        warehouse_costs = np.random.randint(100, 300, size=graph.number_of_nodes)
        delivery_costs = np.random.rand(graph.number_of_nodes, graph.number_of_nodes) * 50
        
        max_budget = np.random.randint(1000, 5000)
        min_warehouses = 2
        max_warehouses = 10
        warehouse_capacities = np.random.randint(100, self.max_capacity, size=graph.number_of_nodes)
        service_penalties = np.random.randint(10, 50, size=graph.number_of_nodes)

        # Additional parameters for new constraints
        raw_material_limits = np.random.randint(50, 200, size=graph.number_of_nodes)
        energy_consumption_coeffs = np.random.rand(graph.number_of_nodes) * 10
        waste_penalties = np.random.randint(10, 100, size=graph.number_of_nodes)
        
        res = {
            'graph': graph,
            'demands': demands,
            'populations': populations,
            'distances': distances,
            'warehouse_costs': warehouse_costs,
            'delivery_costs': delivery_costs,
            'max_budget': max_budget,
            'min_warehouses': min_warehouses,
            'max_warehouses': max_warehouses,
            'warehouse_capacities': warehouse_capacities,
            'service_penalties': service_penalties,
            'raw_material_limits': raw_material_limits,
            'energy_consumption_coeffs': energy_consumption_coeffs,
            'waste_penalties': waste_penalties,
        }
        return res

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        graph = instance['graph']
        demands = instance['demands']
        warehouse_costs = instance['warehouse_costs']
        delivery_costs = instance['delivery_costs']
        max_budget = instance['max_budget']
        min_warehouses = instance['min_warehouses']
        max_warehouses = instance['max_warehouses']
        distances = instance['distances']
        warehouse_capacities = instance['warehouse_capacities']
        service_penalties = instance['service_penalties']
        raw_material_limits = instance['raw_material_limits']
        energy_consumption_coeffs = instance['energy_consumption_coeffs']
        waste_penalties = instance['waste_penalties']

        model = Model("WarehouseAllocationOptimization")

        # Add variables
        warehouse_vars = {node: model.addVar(vtype="B", name=f"WarehouseSelection_{node}") for node in graph.nodes}
        delivery_vars = {(i, j): model.addVar(vtype="B", name=f"DeliveryRouting_{i}_{j}") for i in graph.nodes for j in graph.nodes}
        penalty_vars = {node: model.addVar(vtype="C", name=f"Penalty_{node}") for node in graph.nodes}

        # New variables for inventory, energy, and waste management
        inventory_vars = {node: model.addVar(vtype="C", name=f"Inventory_{node}") for node in graph.nodes}
        energy_vars = {node: model.addVar(vtype="C", name=f"Energy_{node}") for node in graph.nodes}
        waste_vars = {node: model.addVar(vtype="C", name=f"Waste_{node}") for node in graph.nodes}

        # Number of warehouses constraint
        model.addCons(quicksum(warehouse_vars[node] for node in graph.nodes) >= min_warehouses, name="MinWarehouses")
        model.addCons(quicksum(warehouse_vars[node] for node in graph.nodes) <= max_warehouses, name="MaxWarehouses")

        # Demand satisfaction constraints with penalties
        for zone in graph.nodes:
            model.addCons(
                quicksum(delivery_vars[zone, warehouse] for warehouse in graph.nodes) + penalty_vars[zone] == 1, 
                name=f"Demand_{zone}"
            )

        # Routing from open warehouses
        for i in graph.nodes:
            for j in graph.nodes:
                model.addCons(delivery_vars[i, j] <= warehouse_vars[j], name=f"Service_{i}_{j}")

        # Capacity constraints
        for j in graph.nodes:
            model.addCons(quicksum(delivery_vars[i, j] * demands[i] for i in graph.nodes) <= warehouse_capacities[j], name=f"Capacity_{j}")

        # Budget constraints
        total_cost = quicksum(warehouse_vars[node] * warehouse_costs[node] for node in graph.nodes) + \
                     quicksum(delivery_vars[i, j] * delivery_costs[i, j] for i in graph.nodes for j in graph.nodes) + \
                     quicksum(penalty_vars[node] * service_penalties[node] for node in graph.nodes)

        model.addCons(total_cost <= max_budget, name="Budget")

        # New raw material constraints
        for node in graph.nodes:
            model.addCons(inventory_vars[node] <= raw_material_limits[node], name=f"RawMaterial_{node}")

        # New energy consumption constraints
        total_energy = quicksum(energy_vars[node] * energy_consumption_coeffs[node] for node in graph.nodes)
        model.addCons(total_energy <= self.max_energy_consumption, name="Energy")

        # New waste generation constraints
        total_waste = quicksum(waste_vars[node] for node in graph.nodes)
        model.addCons(total_waste <= self.max_waste_threshold, name="Waste")

        # New objective: Minimize total cost including energy and waste penalties
        objective = total_cost + quicksum(energy_vars[node] for node in graph.nodes) + quicksum(waste_vars[node] * waste_penalties[node] for node in graph.nodes)
        model.setObjective(objective, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_nodes': 82,
        'edge_probability': 0.78,
        'graph_type': 'watts_strogatz',
        'k': 56,
        'rewiring_prob': 0.76,
        'max_capacity': 1750,
        'max_energy_consumption': 5000,
        'max_waste_threshold': 2000,
    }

    warehouse_allocation_optimization = WarehouseAllocationOptimization(parameters, seed=seed)
    instance = warehouse_allocation_optimization.generate_instance()
    solve_status, solve_time = warehouse_allocation_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")