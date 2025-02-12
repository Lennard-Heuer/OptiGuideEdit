import random
import time
import numpy as np
from pyscipopt import Model, quicksum
import networkx as nx

class EmergencyVehicleOptimization:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)
        self.seed = seed
        if self.seed:
            random.seed(seed)
            np.random.seed(seed)

    ################# Data Generation #################
    def generate_instance(self):
        neighborhoods = range(self.number_of_neighborhoods)
        stations = range(self.potential_stations)
        
        # Generating neighborhood population
        population = np.random.gamma(shape=self.population_shape, scale=self.population_scale, size=self.number_of_neighborhoods).astype(int)
        population = np.clip(population, self.min_population, self.max_population)

        # Generating the emergency response rates
        response_rates = np.random.beta(self.alpha_response_rate, self.beta_response_rate, size=self.number_of_neighborhoods)
        
        # Distance matrix between neighborhoods and potential emergency vehicle stations
        G = nx.barabasi_albert_graph(self.number_of_neighborhoods, self.number_of_graph_edges)
        emergency_distances = nx.floyd_warshall_numpy(G) * np.random.uniform(self.min_distance_multiplier, self.max_distance_multiplier)

        # Generating station costs and capacities
        station_costs = np.random.gamma(self.station_cost_shape, self.station_cost_scale, size=self.potential_stations)
        station_capacities = np.random.gamma(self.station_capacity_shape, self.station_capacity_scale, size=self.potential_stations).astype(int)

        # Emergency energy availability
        energy_availability = np.random.weibull(self.energy_shape, size=self.potential_stations) * self.energy_scale
        
        # Breakpoints for piecewise linear functions
        d_breakpoints = np.linspace(0, 1, self.num_segments + 1)
        transport_costs_segments = np.random.uniform(self.min_transport_cost, self.max_transport_cost, self.num_segments)
        
        res = {
            'population': population, 
            'response_rates': response_rates,
            'emergency_distances': emergency_distances,
            'station_costs': station_costs, 
            'station_capacities': station_capacities,
            'energy_availability': energy_availability,
            'd_breakpoints': d_breakpoints,
            'transport_costs_segments': transport_costs_segments
        }
        
        # New instance data for set covering formulation
        min_emergency_vehicles = np.random.randint(1, self.min_vehicles, size=self.number_of_neighborhoods)
        res['min_emergency_vehicles'] = min_emergency_vehicles
        
        return res        

    ################# PySCIPOpt Modeling #################
    def solve(self, instance):
        population = instance['population']
        response_rates = instance['response_rates']
        emergency_distances = instance['emergency_distances']
        station_costs = instance['station_costs']
        station_capacities = instance['station_capacities']
        energy_availability = instance['energy_availability']
        d_breakpoints = instance['d_breakpoints']
        transport_costs_segments = instance['transport_costs_segments']
        min_emergency_vehicles = instance['min_emergency_vehicles']
        
        neighborhoods = range(len(population))
        stations = range(len(station_costs))
        segments = range(len(transport_costs_segments))
        
        model = Model("EmergencyVehicleOptimization")
        e = {}  # Binary variable: 1 if emergency vehicle station is placed at location l
        v = {}  # Binary variable: 1 if a response route from n to l exists
        b = {}  # Integer variable: Response frequency
        d = {}  # Continuous variable: Fraction of demand satisfied
        z_nl_s = {}  # Binary variable for piecewise linear segment
        cover = {}  # Auxiliary binary variables for set covering
        
        # Decision variables
        for l in stations:
            e[l] = model.addVar(vtype="B", name=f"e_{l}")
            for n in neighborhoods:
                v[n, l] = model.addVar(vtype="B", name=f"v_{n}_{l}")
                b[n, l] = model.addVar(vtype="I", name=f"b_{n}_{l}", lb=0, ub=self.max_response_frequency)
                d[n, l] = model.addVar(vtype="C", name=f"d_{n}_{l}", lb=0, ub=1)
                for s in segments:
                    z_nl_s[n, l, s] = model.addVar(vtype="B", name=f"z_{n}_{l}_{s}")
            cover[l] = model.addVar(vtype="B", name=f"cover_{l}")
        
        # Objective: Minimize response cost + station costs + energy impact + maximize satisfaction
        obj_expr = quicksum(emergency_distances[n][l] * v[n, l] * population[n] * response_rates[n] for n in neighborhoods for l in stations) + \
                   quicksum(station_costs[l] * e[l] for l in stations) + \
                   quicksum((1 - d[n, l]) * population[n] for n in neighborhoods for l in stations) - \
                   quicksum(d[n, l] for n in neighborhoods for l in stations) + \
                   quicksum(transport_costs_segments[s] * z_nl_s[n, l, s] for n in neighborhoods for l in stations for s in segments)
        
        model.setObjective(obj_expr, "minimize")

        # Constraints: Each neighborhood must have access to one emergency vehicle
        for n in neighborhoods:
            model.addCons(
                quicksum(v[n, l] for l in stations) == 1,
                f"EmergencyCoverage_{n}"
            )

        # Constraints: Station capacity must not be exceeded
        for l in stations:
            model.addCons(
                quicksum(v[n, l] * population[n] * response_rates[n] * d[n, l] for n in neighborhoods) <= station_capacities[l] * e[l],
                f"Capacity_{l}"
            )

        # Constraints: Energy availability at each station
        for l in stations:
            model.addCons(
                quicksum(v[n, l] * response_rates[n] * b[n, l] for n in neighborhoods) <= energy_availability[l],
                f"Energy_{l}"
            )

        # Constraints: Response frequency related to demand satisfaction
        for n in neighborhoods:
            for l in stations:
                model.addCons(
                    b[n, l] == population[n] * d[n, l],
                    f"Frequency_Demand_{n}_{l}"
                )
                
        # Piecewise Linear Constraints: Ensure each demand fraction lies within a segment
        for n in neighborhoods:
            for l in stations:
                model.addCons(
                    quicksum(z_nl_s[n, l, s] for s in segments) == 1,
                    f"Segment_{n}_{l}"
                )
                
                for s in segments[:-1]:
                    model.addCons(
                        d[n, l] >= d_breakpoints[s] * z_nl_s[n, l, s],
                        f"LowerBoundSeg_{n}_{l}_{s}"
                    )
                    model.addCons(
                        d[n, l] <= d_breakpoints[s+1] * z_nl_s[n, l, s] + (1 - z_nl_s[n, l, s]) * d_breakpoints[-1],
                        f"UpperBoundSeg_{n}_{l}_{s}"
                    )

        # New Set Covering Constraints
        for n in neighborhoods:
            model.addCons(
                quicksum(v[n, l] for l in stations) >= min_emergency_vehicles[n],
                f"Set_Covering_{n}"
            )
                
        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'number_of_neighborhoods': 75,
        'potential_stations': 25,
        'population_shape': 25,
        'population_scale': 300,
        'min_population': 2500,
        'max_population': 3000,
        'alpha_response_rate': 6.0,
        'beta_response_rate': 3.75,
        'number_of_graph_edges': 30,
        'min_distance_multiplier': 1,
        'max_distance_multiplier': 18,
        'station_cost_shape': 5.0,
        'station_cost_scale': 2000.0,
        'station_capacity_shape': 50.0,
        'station_capacity_scale': 400.0,
        'energy_shape': 0.5,
        'energy_scale': 10000,
        'max_response_frequency': 50,
        'num_segments': 5,
        'min_transport_cost': 1.0,
        'max_transport_cost': 10.0,
        'min_vehicles': 2
    }
    
    emergency_vehicle_optimization = EmergencyVehicleOptimization(parameters, seed=seed)
    instance = emergency_vehicle_optimization.generate_instance()
    solve_status, solve_time = emergency_vehicle_optimization.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")