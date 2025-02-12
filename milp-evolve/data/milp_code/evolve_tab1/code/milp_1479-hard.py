import random
import time
import numpy as np
from pyscipopt import Model, quicksum

class HospitalBedOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    def generate_instance(self):
        assert self.n_hospitals > 0 and self.n_zones > 0
        assert self.min_hospital_cost >= 0 and self.max_hospital_cost >= self.min_hospital_cost
        assert self.min_transport_cost >= 0 and self.max_transport_cost >= self.min_transport_cost
        assert self.min_bed_capacity > 0 and self.max_bed_capacity >= self.min_bed_capacity

        hospital_costs = np.random.randint(self.min_hospital_cost, self.max_hospital_cost + 1, self.n_hospitals)
        transport_costs = np.random.randint(self.min_transport_cost, self.max_transport_cost + 1, (self.n_hospitals, self.n_zones))
        bed_capacities = np.random.randint(self.min_bed_capacity, self.max_bed_capacity + 1, self.n_hospitals)
        patient_needs = np.random.randint(1, 10, self.n_zones)
        equipment_limits = np.random.uniform(self.min_equipment_limit, self.max_equipment_limit, self.n_hospitals)
        distances = np.random.uniform(0, self.max_distance, (self.n_hospitals, self.n_zones))
        
        return {
            "hospital_costs": hospital_costs,
            "transport_costs": transport_costs,
            "bed_capacities": bed_capacities,
            "patient_needs": patient_needs,
            "equipment_limits": equipment_limits,
            "distances": distances,
        }

    def solve(self, instance):
        hospital_costs = instance['hospital_costs']
        transport_costs = instance['transport_costs']
        bed_capacities = instance['bed_capacities']
        patient_needs = instance['patient_needs']
        equipment_limits = instance['equipment_limits']
        distances = instance['distances']

        model = Model("HospitalBedOptimization")
        n_hospitals = len(hospital_costs)
        n_zones = len(transport_costs[0])

        # Decision variables
        open_vars = {h: model.addVar(vtype="B", name=f"Hospital_{h}") for h in range(n_hospitals)}
        bed_vars = {(h, z): model.addVar(vtype="C", name=f"Beds_{h}_{z}") for h in range(n_hospitals) for z in range(n_zones)}
        serve_vars = {(h, z): model.addVar(vtype="B", name=f"Serve_{h}_{z}") for h in range(n_hospitals) for z in range(n_zones)}

        # Objective: minimize the total cost including hospital operating costs and transport costs.
        model.setObjective(
            quicksum(hospital_costs[h] * open_vars[h] for h in range(n_hospitals)) +
            quicksum(transport_costs[h, z] * bed_vars[h, z] for h in range(n_hospitals) for z in range(n_zones)),
            "minimize"
        )

        # Constraints: Each zone's patient needs are met by the hospitals
        for z in range(n_zones):
            model.addCons(quicksum(bed_vars[h, z] for h in range(n_hospitals)) == patient_needs[z], f"Zone_{z}_Patient_Needs")
        
        # Constraints: Only open hospitals can allocate beds
        for h in range(n_hospitals):
            for z in range(n_zones):
                model.addCons(bed_vars[h, z] <= equipment_limits[h] * open_vars[h], f"Hospital_{h}_Serve_{z}")
        
        # Constraints: Hospitals cannot exceed their bed capacities
        for h in range(n_hospitals):
            model.addCons(quicksum(bed_vars[h, z] for z in range(n_zones)) <= bed_capacities[h], f"Hospital_{h}_Bed_Capacity")

        # Movement distance constraint (Critical zone) using Big M Formulation
        M = self.max_distance * 100  # Big M value to enforce logical constraints
        for z in range(n_zones):
            for h in range(n_hospitals):
                model.addCons(serve_vars[h, z] <= open_vars[h], f"Serve_Open_Constraint_{h}_{z}")
                model.addCons(distances[h, z] * open_vars[h] <= self.max_distance + M * (1 - serve_vars[h, z]), f"Distance_Constraint_{h}_{z}")
            model.addCons(quicksum(serve_vars[h, z] for h in range(n_hospitals)) >= 1, f"Zone_{z}_Critical")

        start_time = time.time()
        model.optimize()
        end_time = time.time()

        return model.getStatus(), end_time - start_time, model.getObjVal()

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_hospitals': 210,
        'n_zones': 60,
        'min_transport_cost': 750,
        'max_transport_cost': 900,
        'min_hospital_cost': 1600,
        'max_hospital_cost': 1875,
        'min_bed_capacity': 1000,
        'max_bed_capacity': 1000,
        'min_equipment_limit': 540,
        'max_equipment_limit': 1900,
        'max_distance': 2100,
    }
    
    hospital_optimizer = HospitalBedOptimization(parameters, seed=seed)
    instance = hospital_optimizer.generate_instance()
    solve_status, solve_time, objective_value = hospital_optimizer.solve(instance)
    
    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")
    print(f"Objective Value: {objective_value:.2f}")