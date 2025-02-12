import random
import time
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum, multidict

class AdvancedFacilityLocation:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        if seed:
            random.seed(seed)
            np.random.seed(seed)
    
    ################# data generation #################
    def randint(self, size, interval):
        return np.random.randint(interval[0], interval[1], size)
    
    def generate_transportation_costs(self, graph, node_positions, customers, facilities):
        m = len(customers)
        n = len(facilities)
        costs = np.zeros((m, n))
        for i in range(m):
            for j in range(n):
                customer_node = customers[i]
                facility_node = facilities[j]
                path_length = nx.shortest_path_length(graph, source=customer_node, target=facility_node, weight='weight')
                costs[i, j] = path_length
        return costs

    def generate_instance(self):
        # Generate customers and facility nodes in a random graph
        graph = nx.random_geometric_graph(self.n_nodes, radius=self.radius)
        pos = nx.get_node_attributes(graph, 'pos')
        customers = random.sample(list(graph.nodes), self.n_customers)
        facilities = random.sample(list(graph.nodes), self.n_facilities)
        
        demands = np.random.poisson(self.avg_demand, self.n_customers)
        capacities = self.randint(self.n_facilities, self.capacity_interval)
        fixed_costs = self.randint(self.n_facilities, self.fixed_cost_interval)
        transportation_costs = self.generate_transportation_costs(graph, pos, customers, facilities)

        vehicle_capacities = self.randint(self.n_vehicle_types, self.vehicle_capacity_interval)
        vehicle_costs_per_km = np.random.uniform(self.vehicle_cost_min, self.vehicle_cost_max, self.n_vehicle_types)
        
        res = {
            'demands': demands,
            'capacities': capacities,
            'fixed_costs': fixed_costs,
            'transportation_costs': transportation_costs,
            'vehicle_capacities': vehicle_capacities,
            'vehicle_costs_per_km': vehicle_costs_per_km
        }

        # New data from the second MILP
        factory_costs = np.random.exponential(50, size=self.n_facilities).tolist()
        order_demands = demands  # Reusing demands as order demands
        res['factory_costs'] = factory_costs
        res['order_demands'] = order_demands
        
        # New stochastic data
        demand_scenarios = np.random.normal(demands, scale=self.demand_std_deviation, size=(self.n_scenarios, self.n_customers))
        transportation_cost_scenarios = np.array([self.generate_transportation_costs(graph, pos, customers, facilities) for _ in range(self.n_scenarios)])
        res['demand_scenarios'] = demand_scenarios
        res['transportation_cost_scenarios'] = transportation_cost_scenarios

        # New instance data
        logical_constraints = {(j, k): random.choice([0, 1]) for j in range(self.n_facilities) for k in range(self.n_constraints)}
        res['logical_constraints'] = logical_constraints 
        
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        demands = instance['demands']
        capacities = instance['capacities']
        fixed_costs = instance['fixed_costs']
        transportation_costs = instance['transportation_costs']
        vehicle_capacities = instance['vehicle_capacities']
        vehicle_costs_per_km = instance['vehicle_costs_per_km']
        factory_costs = instance['factory_costs']
        order_demands = instance['order_demands']
        demand_scenarios = instance['demand_scenarios']
        transportation_cost_scenarios = instance['transportation_cost_scenarios']
        logical_constraints = instance['logical_constraints']

        n_customers = len(demands)
        n_facilities = len(capacities)
        n_vehicle_types = len(vehicle_capacities)
        n_scenarios = len(demand_scenarios)
        n_constraints = self.n_constraints

        model = Model("AdvancedFacilityLocation")

        # Decision variables
        open_facilities = {j: model.addVar(vtype="B", name=f"Open_{j}") for j in range(n_facilities)}
        serve = {(i, j): model.addVar(vtype="I", name=f"Serve_{i}_{j}") for i in range(n_customers) for j in range(n_facilities)}
        vehicle_assign = {(j, k): model.addVar(vtype="B", name=f"VehicleAssign_{j}_{k}") for j in range(n_facilities) for k in range(n_vehicle_types)}
        unmet_demand = {i: model.addVar(vtype="I", name=f"UnmetDemand_{i}") for i in range(n_customers)}
        allocation_vars = {(i, j): model.addVar(vtype="C", name=f"Alloc_{i}_{j}") for j in range(n_facilities) for i in range(n_customers)}
        factory_usage_vars = {j: model.addVar(vtype="B", name=f"FactoryUsage_{j}") for j in range(n_facilities)}
        scenario_unmet_demand = {(s, i): model.addVar(vtype="I", name=f"ScenarioUnmetDemand_{s}_{i}") for s in range(n_scenarios) for i in range(n_customers)}
        
        logical_vars = {(j, k): model.addVar(vtype="B", name=f"LogicalVar_{j}_{k}") for j in range(n_facilities) for k in range(n_constraints)}

        # Objective: minimize total cost including penalties for unmet demand
        fixed_costs_expr = quicksum(fixed_costs[j] * open_facilities[j] for j in range(n_facilities))
        transportation_costs_expr = quicksum(transportation_costs[i, j] * serve[i, j] for i in range(n_customers) for j in range(n_facilities))
        vehicle_costs_expr = quicksum(vehicle_costs_per_km[k] * vehicle_assign[j, k] * capacities[j] for j in range(n_facilities) for k in range(n_vehicle_types))
        factory_costs_expr = quicksum(factory_costs[j] * factory_usage_vars[j] for j in range(n_facilities))
        unmet_demand_penalty = 1000  # Arbitrary large penalty for unmet demand
        scenario_penalty = 500   # Additional penalty for stochastic scenarios

        objective_expr = (
            fixed_costs_expr 
            + transportation_costs_expr 
            + vehicle_costs_expr 
            + factory_costs_expr 
            + quicksum(unmet_demand_penalty * unmet_demand[i] for i in range(n_customers))
            + quicksum(scenario_penalty * scenario_unmet_demand[s, i] for s in range(n_scenarios) for i in range(n_customers))
        )

        # Constraints: demand must be met or penalized
        for i in range(n_customers):
            model.addCons(quicksum(serve[i, j] for j in range(n_facilities)) + unmet_demand[i] == demands[i], f"Demand_{i}")
        
        # Constraints: capacity limits
        for j in range(n_facilities):
            model.addCons(quicksum(serve[i, j] for i in range(n_customers)) <= capacities[j] * open_facilities[j], f"Capacity_{j}")

        # Constraints: vehicle capacity limits
        for j in range(n_facilities):
            model.addCons(quicksum(vehicle_assign[j, k] * vehicle_capacities[k] for k in range(n_vehicle_types)) >= capacities[j] * open_facilities[j], f"VehicleCapacity_{j}")

        # Constraints: tightening constraints
        for j in range(n_facilities):
            for i in range(n_customers):
                model.addCons(serve[i, j] <= open_facilities[j] * demands[i], f"Tightening_{i}_{j}")
        
        # New Constraints: Satisfy order demands
        for i in range(n_customers):
            model.addCons(quicksum(allocation_vars[i, j] for j in range(n_facilities)) == order_demands[i], f"OrderDemand_{i}")
        
        # New Constraints: Factory capacity limits
        for j in range(n_facilities):
            model.addCons(quicksum(allocation_vars[i, j] for i in range(n_customers)) <= capacities[j] * factory_usage_vars[j], f"FactoryCapacity_{j}")

        # New Constraints: Stochastic demand coverage
        for s in range(n_scenarios):
            for i in range(n_customers):
                scenario_demand = demand_scenarios[s, i]
                model.addCons(
                    quicksum(serve[i, j] for j in range(n_facilities)) + scenario_unmet_demand[s, i] >= scenario_demand, f"ScenarioDemand_{s}_{i}"
                )
        
        # Convex Hull Constraints: Logical relationships
        for j in range(n_facilities):
            for k in range(n_constraints):
                model.addCons(logical_vars[j, k] == open_facilities[j] * logical_constraints[j, k], f"Logical_{j}_{k}")
        
        model.setObjective(objective_expr, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_customers': 37,
        'n_facilities': 56,
        'n_nodes': 112,
        'radius': 0.17,
        'avg_demand': 70,
        'capacity_interval': (75, 1207),
        'fixed_cost_interval': (500, 555),
        'vehicle_capacity_interval': (562, 1125),
        'vehicle_cost_min': 6.75,
        'vehicle_cost_max': 10.0,
        'n_vehicle_types': 135,
        'min_demand': 15,
        'max_demand': 1500,
        'min_capacity': 2700,
        'max_capacity': 3000,
        'demand_std_deviation': 200,
        'n_scenarios': 50,
        'n_constraints': 35,
    }
    
    facility_location = AdvancedFacilityLocation(parameters, seed=seed)
    instance = facility_location.generate_instance()
    solve_status, solve_time = facility_location.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")