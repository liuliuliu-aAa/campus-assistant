class NoAvailableAgentError(Exception):
    pass


def select_agent(agent_pool, task):
    candidates = [a for a in agent_pool if a.supports(task.type)]
    if not candidates:
        raise NoAvailableAgentError(task.type)
    return min(candidates, key=lambda a: a.current_load * 0.6 + a.avg_response_time * 0.4)
# 优先级公式 Priority = w1 × Urgency + w2 × UserPriority + w3 × Freshness + w4 × DependencyDepth
