import random
import time
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum

class FLIMP:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)
    
    ################# Data Generation #################
    def generate_random_graph(self):
        facilities = np.random.randint(self.min_facilities, self.max_facilities)
        customers = np.random.randint(self.min_customers, self.max_customers)
        return nx.complete_bipartite_graph(facilities, customers)

    def generate_costs_capacities(self, G):
        self.facility_opening_costs = {node: np.random.randint(self.min_opening_cost, self.max_opening_cost)
                                       for node in range(self.max_facilities)}
        self.holding_costs = {node: np.random.rand()*self.max_holding_cost for node in range(self.max_facilities)}
        self.capacity = {node: np.random.randint(self.min_capacity, self.max_capacity)
                         for node in range(self.max_facilities)}
        self.customer_demand = {node: np.random.randint(self.min_demand, self.max_demand)
                                for node in range(self.max_facilities, self.max_facilities+self.max_customers)}
        self.transportation_costs = {(fac, cust): np.random.rand()*self.max_transport_cost
                                     for fac in range(self.max_facilities)
                                     for cust in range(self.max_facilities, self.max_facilities+self.max_customers)}

    def generate_instance(self):
        G = self.generate_random_graph()
        self.generate_costs_capacities(G)
        
        res = {
            'G': G,
            'facility_opening_costs': self.facility_opening_costs,
            'holding_costs': self.holding_costs,
            'capacity': self.capacity,
            'customer_demand': self.customer_demand,
            'transportation_costs': self.transportation_costs
        }
        return res
    
    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        G, facility_opening_costs, holding_costs, capacity, customer_demand, transportation_costs = \
            instance.values()

        model = Model("Facility_Location_Inventory_Management")
        
        # Variables
        facility_vars = {f"F{node}": model.addVar(vtype="B", name=f"F{node}") 
                         for node in range(self.max_facilities)}
        transportation_vars = {f"T{fac}_{cust}": model.addVar(vtype="C", name=f"T{fac}_{cust}")
                               for fac in range(self.max_facilities)
                               for cust in range(self.max_facilities, self.max_facilities+self.max_customers)}
        allocation_vars = {f"A{fac}_{cust}": model.addVar(vtype="B", name=f"A{fac}_{cust}")
                           for fac in range(self.max_facilities)
                           for cust in range(self.max_facilities, self.max_facilities+self.max_customers)}
        inventory_vars = {f"I{fac}_{t}": model.addVar(vtype="C", name=f"I{fac}_{t}")
                          for fac in range(self.max_facilities)
                          for t in range(self.time_horizon)}

        # Objective function: Minimize costs (facility opening, transportation, holding)
        obj_expr = quicksum(facility_opening_costs[fac] * facility_vars[f"F{fac}"]
                            for fac in range(self.max_facilities)) + \
                   quicksum(transportation_costs[fac, cust] * transportation_vars[f"T{fac}_{cust}"]
                            for fac in range(self.max_facilities)
                            for cust in range(self.max_facilities, self.max_facilities+self.max_customers)) + \
                   quicksum(holding_costs[fac] * inventory_vars[f"I{fac}_{t}"]
                            for fac in range(self.max_facilities)
                            for t in range(self.time_horizon))

        # Constraints
        # Facility capacity constraints
        for fac in range(self.max_facilities):
            model.addCons(
                quicksum(transportation_vars[f"T{fac}_{cust}"] for cust in range(self.max_facilities, self.max_facilities+self.max_customers))
                <= capacity[fac] * facility_vars[f"F{fac}"],
                name=f"Capacity_{fac}")

        # Customer demand satisfaction constraints
        for cust in range(self.max_facilities, self.max_facilities+self.max_customers):
            model.addCons(
                quicksum(transportation_vars[f"T{fac}_{cust}"] for fac in range(self.max_facilities)) 
                >= customer_demand[cust],
                name=f"Demand_{cust}")

        # Allocation and transportation consistency constraints
        for fac in range(self.max_facilities):
            for cust in range(self.max_facilities, self.max_facilities+self.max_customers):
                model.addCons(
                    transportation_vars[f"T{fac}_{cust}"] <= self.big_m * allocation_vars[f"A{fac}_{cust}"],
                    name=f"Trans_Alloc_{fac}_{cust}")

        # Inventory balance constraints over time
        for fac in range(self.max_facilities):
            for t in range(1, self.time_horizon):
                model.addCons(
                    inventory_vars[f"I{fac}_{t}"] == inventory_vars[f"I{fac}_{t-1}"] +
                    quicksum(transportation_vars[f"T{fac}_{cust}"] for cust in range(self.max_facilities, self.max_facilities + self.max_customers))
                    - quicksum(transportation_vars[f"T{fac}_{cust}"] for fac in range(self.max_facilities)), 
                    name=f"Inventory_{fac}_{t}")

        # Setting objective and solving
        model.setObjective(obj_expr, "minimize")
        
        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'min_facilities': 30,
        'max_facilities': 50,
        'min_customers': 60,
        'max_customers': 100,
        'min_opening_cost': 5000,
        'max_opening_cost': 20000,
        'min_capacity': 100,
        'max_capacity': 2000,
        'min_demand': 50,
        'max_demand': 250,
        'max_transport_cost': 100,
        'max_holding_cost': 16,
        'time_horizon': 12,
        'big_m': 100000,
    }
    
    flimp = FLIMP(parameters, seed=seed)
    instance = flimp.generate_instance()
    solve_status, solve_time = flimp.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")