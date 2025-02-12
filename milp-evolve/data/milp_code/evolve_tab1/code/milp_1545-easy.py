import random
import time
import numpy as np
from pyscipopt import Model, quicksum

class ShipmentDeliveryOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_instance(self):
        weights = np.random.normal(loc=self.weight_mean, scale=self.weight_std, size=self.number_of_deliveries).astype(int)
        profits = weights + np.random.normal(loc=self.profit_mean_shift, scale=self.profit_std, size=self.number_of_deliveries).astype(int)

        # Ensure non-negative values
        weights = np.clip(weights, self.min_range, self.max_range)
        profits = np.clip(profits, self.min_range, self.max_range)

        cargo_volume_capacities = np.zeros(self.number_of_vehicles, dtype=int)
        cargo_volume_capacities[:-1] = np.random.randint(0.4 * weights.sum() // self.number_of_vehicles,
                                                         0.6 * weights.sum() // self.number_of_vehicles,
                                                         self.number_of_vehicles - 1)
        cargo_volume_capacities[-1] = 0.5 * weights.sum() - cargo_volume_capacities[:-1].sum()

        handling_times = np.random.uniform(1, 5, self.number_of_vehicles)  # Handling times between 1 and 5 hours per delivery
        handling_time_penalty = np.random.uniform(20, 50, self.number_of_vehicles)  # Handling time penalty between $20 and $50 per hour

        # New data for added complexity
        delivery_deadlines = np.random.uniform(1, 10, self.number_of_deliveries)  # Random deadlines between 1 and 10 hours
        vehicle_speeds = np.random.uniform(30, 60, self.number_of_vehicles)  # Random speeds between 30 and 60 km/h

        # Data for energy and emission constraints
        max_energy_consumption = np.random.uniform(1000, 5000, size=self.number_of_vehicles)
        emission_rates = np.random.uniform(0.1, 1.0, size=(self.number_of_deliveries, self.number_of_vehicles))

        # Data for knapsack constraints
        item_weights = np.random.randint(1, 10, size=(self.number_of_deliveries,))
        item_profits = np.random.randint(10, 100, size=(self.number_of_deliveries,))

        res = {
            'weights': weights, 
            'profits': profits, 
            'cargo_volume_capacities': cargo_volume_capacities,
            'handling_times': handling_times,
            'handling_time_penalty': handling_time_penalty,
            'delivery_deadlines': delivery_deadlines,
            'vehicle_speeds': vehicle_speeds,
            'max_energy_consumption': max_energy_consumption,
            'emission_rates': emission_rates,
            'item_weights': item_weights,
            'item_profits': item_profits
        }

        return res

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        weights = instance['weights']
        profits = instance['profits']
        cargo_volume_capacities = instance['cargo_volume_capacities']
        handling_times = instance['handling_times']
        handling_time_penalty = instance['handling_time_penalty']
        delivery_deadlines = instance['delivery_deadlines']
        vehicle_speeds = instance['vehicle_speeds']
        max_energy_consumption = instance['max_energy_consumption']
        emission_rates = instance['emission_rates']
        item_weights = instance['item_weights']
        item_profits = instance['item_profits']
        
        number_of_deliveries = len(weights)
        number_of_vehicles = len(cargo_volume_capacities)

        model = Model("ShipmentDeliveryOptimization")
        var_names = {}
        start_times = {}
        z = {}
        energy_vars = {}
        emission_vars = {}

        # Decision variables: x[i][j] = 1 if delivery i is assigned to vehicle j
        for i in range(number_of_deliveries):
            for j in range(number_of_vehicles):
                var_names[(i, j)] = model.addVar(vtype="B", name=f"x_{i}_{j}")
                start_times[(i, j)] = model.addVar(vtype="C", lb=0, ub=delivery_deadlines[i], name=f"start_time_{i}_{j}")
                emission_vars[(i, j)] = model.addVar(vtype="C", name=f"emission_{i}_{j}")
            z[i] = model.addVar(vtype="B", name=f"z_{i}")

        # Energy consumption variables for each vehicle
        for j in range(number_of_vehicles):
            energy_vars[j] = model.addVar(vtype="C", name=f"Energy_{j}")

        # Objective: Maximize total profit considering handling time cost, energy, and emissions
        objective_expr = quicksum((profits[i] * (j+1)) * var_names[(i, j)] for i in range(number_of_deliveries) for j in range(number_of_vehicles))
        handling_cost = quicksum(handling_time_penalty[j] * handling_times[j] for j in range(number_of_vehicles))
        energy_penalty = quicksum(energy_vars[j] for j in range(number_of_vehicles))
        emission_penalty = quicksum(emission_vars[(i, j)] for i in range(number_of_deliveries) for j in range(number_of_vehicles))

        # Objective function considering handling cost, energy consumption, and emissions
        objective_expr -= (handling_cost + energy_penalty + emission_penalty)

        # Constraints: Each delivery can be assigned to at most one vehicle
        for i in range(number_of_deliveries):
            model.addCons(
                quicksum(var_names[(i, j)] for j in range(number_of_vehicles)) <= z[i],
                f"DeliveryAssignment_{i}"
            )

        # Constraints: Total weight in each vehicle must not exceed its capacity
        for j in range(number_of_vehicles):
            model.addCons(
                quicksum(weights[i] * var_names[(i, j)] for i in range(number_of_deliveries)) <= cargo_volume_capacities[j],
                f"VehicleCapacity_{j}"
            )

        # Additional constraints for diversity: ensure minimum utilization of each vehicle
        for j in range(number_of_vehicles):
            model.addCons(
                quicksum(weights[i] * var_names[(i, j)] for i in range(number_of_deliveries)) >= 0.1 * cargo_volume_capacities[j],
                f"VehicleMinUtilization_{j}"
            )

        # Time window constraints: Ensure deliveries meet deadlines
        for i in range(number_of_deliveries):
            for j in range(number_of_vehicles):
                model.addCons(
                    start_times[(i, j)] <= delivery_deadlines[i] * var_names[(i, j)],
                    f"TimeWindow_{i}_{j}"
                )
                model.addCons(
                    start_times[(i, j)] >= (delivery_deadlines[i] - (weights[i] / vehicle_speeds[j])) * var_names[(i, j)],
                    f"StartTimeConstraint_{i}_{j}"
                )

        # Big M Constraints: Ensure z[i] logically connects to x[i][j]
        for i in range(number_of_deliveries):
            for j in range(number_of_vehicles):
                model.addCons(var_names[(i, j)] <= z[i], f"BigM_constraint_1_{i}_{j}")  # If x[i][j] is 1, z[i] must be 1
                model.addCons(var_names[(i, j)] >= z[i] - (1 - var_names[(i, j)]), f"BigM_constraint_2_{i}_{j}")  # If z[i] is 1, at least one x[i][j] must be 1

        # Energy consumption constraints for each vehicle
        for j in range(number_of_vehicles):
            model.addCons(
                energy_vars[j] <= max_energy_consumption[j],
                f"MaxEnergy_{j}"
            )

        # Emission constraints for each delivery route
        for i in range(number_of_deliveries):
            for j in range(number_of_vehicles):
                model.addCons(
                    emission_vars[(i, j)] == emission_rates[(i, j)] * var_names[(i, j)],
                    f"Emission_{i}_{j}"
                )

        model.setObjective(objective_expr, "maximize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'number_of_deliveries': 1500,
        'number_of_vehicles': 4,
        'min_range': 2,
        'max_range': 336,
        'weight_mean': 60,
        'weight_std': 2500,
        'profit_mean_shift': 750,
        'profit_std': 0,
    }
    
    optimizer = ShipmentDeliveryOptimization(parameters, seed=seed)
    instance = optimizer.generate_instance()
    solve_status, solve_time = optimizer.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")