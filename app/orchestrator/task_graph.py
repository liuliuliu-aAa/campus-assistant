class CycleDetectedError(Exception):
    pass


class TaskNode:
    def __init__(self, agent_type, params):
        self.agent_type = agent_type
        self.params = params


class TaskGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_task(self, task_id, agent_type, params, depends_on=()):
        self.nodes[task_id] = TaskNode(agent_type, params)
        for dep in depends_on:
            self.edges.append((dep, task_id))

    def get_execution_plan(self):
        batches, completed = [], set()
        while len(completed) < len(self.nodes):
            ready = [
                tid for tid in self.nodes
                if tid not in completed
                and all(d in completed for d, t in self.edges if t == tid)
            ]
            if not ready:
                raise CycleDetectedError(self.nodes.keys() - completed)
            batches.append(ready)
            completed.update(ready)
        return batches
