import random
import time
import numpy as np
import scipy.sparse
from pyscipopt import Model, quicksum

class EmergencyDroneLogistics:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_instance(self):
        nnzrs = int(self.total_zones * self.total_drones * self.density)

        indices = np.random.choice(self.total_drones, size=nnzrs)
        indices[:2 * self.total_drones] = np.repeat(np.arange(self.total_drones), 2)
        _, drones_per_zone = np.unique(indices, return_counts=True)

        indices[:self.total_zones] = np.random.permutation(self.total_zones)
        i = 0
        indptr = [0]
        for n in drones_per_zone:
            if i >= self.total_zones:
                indices[i:i + n] = np.random.choice(self.total_zones, size=n, replace=False)
            elif i + n > self.total_zones:
                remaining_zones = np.setdiff1d(np.arange(self.total_zones), indices[i:self.total_zones], assume_unique=True)
                indices[self.total_zones:i + n] = np.random.choice(remaining_zones, size=i + n - self.total_zones, replace=False)
            i += n
            indptr.append(i)

        coverage_costs = np.random.randint(self.max_cost, size=self.total_drones) + 1
        A = scipy.sparse.csc_matrix(
            (np.ones(len(indices), dtype=int), indices, indptr),
            shape=(self.total_zones, self.total_drones)).tocsr()
        indices_csr = A.indices
        indptr_csr = A.indptr

        event_costs = np.random.randint(self.event_cost_low, self.event_cost_high, size=self.important_events)
        emergency_service = np.random.choice(self.total_drones, self.important_events, replace=False)

        maintenance_costs = np.random.randint(self.min_maintenance_cost, self.max_maintenance_cost, self.total_drones)
        
        travel_times = np.random.randint(self.min_travel_time, self.max_travel_time, (self.total_vehicles, self.total_drones))
        vehicle_capacities = np.random.randint(self.min_vehicle_capacity, self.max_vehicle_capacity, self.total_vehicles)

        res = {
            'coverage_costs': coverage_costs,
            'indptr_csr': indptr_csr,
            'indices_csr': indices_csr,
            'emergency_service': emergency_service,
            'event_costs': event_costs,
            'maintenance_costs': maintenance_costs,
            'travel_times': travel_times,
            'vehicle_capacities': vehicle_capacities
        }
        return res

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        coverage_costs = instance['coverage_costs']
        indptr_csr = instance['indptr_csr']
        indices_csr = instance['indices_csr']
        emergency_service = instance['emergency_service']
        event_costs = instance['event_costs']
        maintenance_costs = instance['maintenance_costs']
        travel_times = instance['travel_times']
        vehicle_capacities = instance['vehicle_capacities']

        model = Model("EmergencyDroneLogistics")
        coverage_vars = {}
        maintenance_vars = {}
        vehicle_vars = {}
        vehicle_time_vars = {}

        # Create variables and set objective
        for j in range(self.total_drones):
            coverage_vars[j] = model.addVar(vtype="B", name=f"coverage_{j}", obj=coverage_costs[j])
            maintenance_vars[j] = model.addVar(vtype="I", name=f"maintenance_{j}", obj=maintenance_costs[j])

        for idx, j in enumerate(emergency_service):
            coverage_vars[j] = model.addVar(vtype="B", name=f"important_{j}", obj=event_costs[idx])

        for v in range(self.total_vehicles):
            vehicle_vars[v] = model.addVar(vtype="B", name=f"vehicle_{v}", obj=self.vehicle_operational_cost)
            for j in range(self.total_drones):
                vehicle_time_vars[(v, j)] = model.addVar(vtype="B", name=f"vehicle_{v}_drone_{j}")

        # Add constraints to ensure each zone is covered
        for zone in range(self.total_zones):
            drones = indices_csr[indptr_csr[zone]:indptr_csr[zone + 1]]
            model.addCons(quicksum(coverage_vars[j] for j in drones) >= 1, f"zone_coverage_{zone}")

        # Maintenance constraints for drones
        for j in range(self.total_drones):
            model.addCons(quicksum(vehicle_time_vars[(v, j)] for v in range(self.total_vehicles)) <= self.max_flight_time_before_maintenance, f"maintenance_limit_{j}")
            model.addCons(maintenance_vars[j] >= quicksum(vehicle_time_vars[(v, j)] for v in range(self.total_vehicles)), f"maintenance_required_{j}")

        # Vehicle capacity constraints
        for v in range(self.total_vehicles):
            model.addCons(quicksum(vehicle_time_vars[(v, j)] for j in range(self.total_drones)) <= vehicle_capacities[v], f"vehicle_capacity_{v}")

        # Enhanced objective
        obj_expr = quicksum(coverage_vars[j] * coverage_costs[j] for j in range(self.total_drones)) + \
                   quicksum(maintenance_vars[j] * maintenance_costs[j] for j in range(self.total_drones)) + \
                   quicksum(vehicle_vars[v] * self.vehicle_operational_cost for v in range(self.total_vehicles)) + \
                   quicksum(travel_times[v][j] * vehicle_time_vars[(v, j)] for v in range(self.total_vehicles) for j in range(self.total_drones))
        model.setObjective(obj_expr, "minimize")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'total_zones': 250,
        'total_drones': 600,
        'density': 0.24,
        'max_cost': 10,
        'important_events': 250,
        'event_cost_low': 375,
        'event_cost_high': 1875,
        'min_maintenance_cost': 100,
        'max_maintenance_cost': 300,
        'total_vehicles': 75,
        'min_vehicle_cost': 2000,
        'max_vehicle_cost': 2400,
        'min_travel_time': 90,
        'max_travel_time': 1500,
        'min_vehicle_capacity': 150,
        'max_vehicle_capacity': 750,
        'vehicle_operational_cost': 500,
        'max_flight_time_before_maintenance': 50
    }
    
    emergency_drone_logistics = EmergencyDroneLogistics(parameters, seed=seed)
    instance = emergency_drone_logistics.generate_instance()
    solve_status, solve_time = emergency_drone_logistics.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")