import random
import time
import numpy as np
import networkx as nx
from pyscipopt import Model, quicksum, multidict

class NetworkMaintenanceAndCybersecurity:
    def __init__(self, parameters, seed=None):
        for key, value in parameters.items():
            setattr(self, key, value)

        if seed:
            random.seed(seed)
            np.random.seed(seed)
    
    ################# Data generation #################
    def randint(self, size, interval):
        return np.random.randint(interval[0], interval[1], size)
    
    def unit_task_assignment_costs(self):
        scaling = 10.0
        rand = lambda n, m: np.random.rand(n, m)
        costs = scaling * np.sqrt(
            (rand(self.n_tasks, 1) - rand(1, self.n_servers))**2 +
            (rand(self.n_tasks, 1) - rand(1, self.n_servers))**2
        )
        return costs

    def generate_instance(self):
        task_demands = self.randint(self.n_tasks, self.task_demand_interval)
        server_capacities = self.randint(self.n_servers, self.server_capacity_interval)
        maintenance_costs = (
            self.randint(self.n_servers, self.maintenance_cost_scale_interval) * np.sqrt(server_capacities) +
            self.randint(self.n_servers, self.maintenance_cost_cste_interval)
        )
        task_assignment_costs = self.unit_task_assignment_costs() * task_demands[:, np.newaxis]

        server_capacities = server_capacities * self.ratio * np.sum(task_demands) / np.sum(server_capacities)
        server_capacities = np.round(server_capacities)
        
        res = {
            'task_demands': task_demands,
            'server_capacities': server_capacities,
            'maintenance_costs': maintenance_costs,
            'task_assignment_costs': task_assignment_costs
        }

        # Cybersecurity implementation costs for each cybersecurity method at each server
        cybersecurity_costs = self.randint((self.n_servers, self.n_cybersecurity_methods), self.cybersecurity_cost_interval)

        # Penalty costs for machine failures due to excessive load
        machine_failure_penalties = self.randint(self.n_servers, self.failure_penalty_interval)

        res.update({
            'cybersecurity_costs': cybersecurity_costs,
            'machine_failure_penalties': machine_failure_penalties
        })

        n_edges = (self.n_servers * (self.n_servers - 1)) // 4  # About n_servers choose 2 divided by 4 
        G = nx.barabasi_albert_graph(self.n_servers, int(np.ceil(n_edges / self.n_servers)))
        clusters = list(nx.find_cliques(G))
        random_clusters = [cl for cl in clusters if len(cl) > 2][:self.max_clusters]
        res['clusters'] = random_clusters
        
        return res

    ################# PySCIPOpt modeling #################
    def solve(self, instance):
        task_demands = instance['task_demands']
        server_capacities = instance['server_capacities']
        maintenance_costs = instance['maintenance_costs']
        task_assignment_costs = instance['task_assignment_costs']
        cybersecurity_costs = instance['cybersecurity_costs']
        machine_failure_penalties = instance['machine_failure_penalties']
        clusters = instance['clusters']
        
        n_tasks = len(task_demands)
        n_servers = len(server_capacities)
        M = np.max(task_demands)
        
        model = Model("NetworkMaintenanceAndCybersecurity")
        
        # Decision variables
        operational_servers = {j: model.addVar(vtype="B", name=f"Operational_{j}") for j in range(n_servers)}
        if self.continuous_assignment:
            assign = {(i, j): model.addVar(vtype="C", name=f"Assign_{i}_{j}") for i in range(n_tasks) for j in range(n_servers)}
        else:
            assign = {(i, j): model.addVar(vtype="B", name=f"Assign_{i}_{j}") for i in range(n_tasks) for j in range(n_servers)}
        
        # Additional variables for different cybersecurity methods
        cybersecurity_protocol = {(j, k): model.addVar(vtype="B", name=f"CybersecurityProtocol_{j}_{k}") for j in range(n_servers) for k in range(self.n_cybersecurity_methods)}

        # Objective: minimize the total cost including maintenance, failure, and cybersecurity implementation
        objective_expr = quicksum(maintenance_costs[j] * operational_servers[j] for j in range(n_servers)) + \
                         quicksum(task_assignment_costs[i, j] * assign[i, j] for i in range(n_tasks) for j in range(n_servers)) + \
                         quicksum(cybersecurity_costs[j, k] * cybersecurity_protocol[j, k] for j in range(n_servers) for k in range(self.n_cybersecurity_methods)) + \
                         quicksum(machine_failure_penalties[j] * operational_servers[j] for j in range(n_servers))
        
        # Constraints: task demand must be met
        for i in range(n_tasks):
            model.addCons(quicksum(assign[i, j] for j in range(n_servers)) >= 1, f"TaskDemand_{i}")
        
        # Constraints: server capacity limits
        for j in range(n_servers):
            model.addCons(quicksum(assign[i, j] * task_demands[i] for i in range(n_tasks)) <= server_capacities[j] * operational_servers[j], f"ServerCapacity_{j}")
        
        # Constraints: tightening constraints
        total_task_demand = np.sum(task_demands)
        model.addCons(quicksum(server_capacities[j] * operational_servers[j] for j in range(n_servers)) >= total_task_demand, "TotalTaskDemand")
        
        for i in range(n_tasks):
            for j in range(n_servers):
                model.addCons(assign[i, j] <= operational_servers[j] * M, f"Tightening_{i}_{j}")

        # Constraints: each server can implement only one cybersecurity protocol
        for j in range(n_servers):
            model.addCons(quicksum(cybersecurity_protocol[j, k] for k in range(self.n_cybersecurity_methods)) == operational_servers[j], f"CybersecurityProtocol_{j}")

        # Constraints: compliance with historic reliability thresholds
        for j in range(n_servers):
            for k in range(self.n_cybersecurity_methods):
                model.addCons(cybersecurity_protocol[j, k] <= self.historic_threshold[k], f"Compliance_{j}_{k}")
                
        # Cluster constraints
        for idx, cluster in enumerate(clusters):
            if len(cluster) > 2:
                model.addCons(quicksum(operational_servers[j] for j in cluster) <= self.compliance_limit, f"Cluster_{idx}")

        model.setObjective(objective_expr, "minimize")
        
        start_time = time.time()
        model.optimize()
        end_time = time.time()
        
        return model.getStatus(), end_time - start_time

if __name__ == '__main__':
    seed = 42
    parameters = {
        'n_tasks': 100,
        'n_servers': 100,
        'n_cybersecurity_methods': 3,
        'task_demand_interval': (5, 36),
        'server_capacity_interval': (10, 161),
        'maintenance_cost_scale_interval': (100, 111),
        'maintenance_cost_cste_interval': (0, 91),
        'ratio': 5.0,
        'cybersecurity_cost_interval': (50, 200),
        'failure_penalty_interval': (10, 50),
        'historic_threshold': [1, 0, 1],  # Example compliance: only methods 0 and 2 are compliant
        'continuous_assignment': True,
        'max_clusters': 10,  # New parameter for controlling the maximum number of clusters
        'compliance_limit': 3,  # New parameter: a limit on how many servers can be simultaneously operational within a cluster
    }
    
    network_maintenance = NetworkMaintenanceAndCybersecurity(parameters, seed=seed)
    instance = network_maintenance.generate_instance()
    solve_status, solve_time = network_maintenance.solve(instance)

    print(f"Solve Status: {solve_status}")
    print(f"Solve Time: {solve_time:.2f} seconds")