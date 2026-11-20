from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time, logging


@dataclass
class AgentResult:
    success: bool
    data: Any
    confidence: float = 1.0
    error: Optional[str] = None
    execution_time: float = 0.0


class BaseAgent(ABC):
    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.logger = logging.getLogger("agent." + name)
        self.metrics = {"total": 0, "success": 0, "fail": 0}

    @abstractmethod
    async def execute(self, task: Dict) -> AgentResult:
        pass

    async def run(self, task: Dict) -> AgentResult:
        start = time.time()
        self.metrics["total"] += 1
        try:
            result = await self.execute(task)
            result.execution_time = time.time() - start
            self.metrics["success" if result.success else "fail"] += 1
            return result
        except Exception as exc:
            self.metrics["fail"] += 1
            self.logger.exception("agent error")
            return AgentResult(False, None, error=str(exc))
