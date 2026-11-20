"""请求 / 响应数据模型：main.py 各路由的接口契约。

- 优先使用 pydantic dataclass（有校验）；pydantic 缺失时自动退化为标准库 dataclass，
  模块可正常 import，不会拖垮应用启动；
- 字段与 main.py 现有路由入参 / 出参一致：collect / classify / summarize / qa / reminders /
  validate / study-outline / pipeline / agents metrics，以及统一响应包装；
- 只声明数据结构，不含业务逻辑。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from pydantic.dataclasses import dataclass as _pydantic_dataclass
    PYDANTIC_AVAILABLE = True
except Exception:  # 缺 pydantic 时退化为标准库 dataclass
    _pydantic_dataclass = None
    PYDANTIC_AVAILABLE = False


def model(cls: Any) -> Any:
    """有 pydantic 时升级为带校验的 dataclass，否则原样返回。"""
    if _pydantic_dataclass is None:
        return cls
    try:
        return _pydantic_dataclass(cls)
    except Exception:
        return cls


@model
@dataclass
class FileItem:
    """采集 / 解析用的文件条目。"""
    document_id: Optional[str] = None
    original_filename: Optional[str] = None
    file_type: Optional[str] = None
    content: Optional[str] = None
    size: Optional[int] = None
    content_hash: Optional[str] = None


@model
@dataclass
class CollectRequest:
    subscriptions: List[Dict[str, Any]] = field(default_factory=list)


@model
@dataclass
class ClassifyRequest:
    files: List[Dict[str, Any]] = field(default_factory=list)


@model
@dataclass
class SummarizeRequest:
    files: List[Dict[str, Any]] = field(default_factory=list)


@model
@dataclass
class QARequest:
    query: str
    course: Optional[str] = None
    top_k: int = 5


@model
@dataclass
class RemindersRequest:
    text: Optional[str] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    channel: Optional[str] = None


@model
@dataclass
class ValidateRequest:
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    classified: Optional[List[Dict[str, Any]]] = None
    summaries: Optional[List[Dict[str, Any]]] = None
    answer: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    reminders: Optional[List[Dict[str, Any]]] = None


@model
@dataclass
class StudyOutlineRequest:
    files: List[Dict[str, Any]] = field(default_factory=list)
    query: Optional[str] = None
    course: Optional[str] = None
    top_k: int = 5


@model
@dataclass
class PipelineRequest:
    subscriptions: List[Dict[str, Any]] = field(default_factory=list)


@model
@dataclass
class AgentMetric:
    agent: str
    total: int = 0
    success: int = 0
    fail: int = 0
    current_load: int = 0
    avg_response_time: float = 0.0


@model
@dataclass
class AgentMetricsData:
    agents: List[AgentMetric] = field(default_factory=list)


@model
@dataclass
class ApiResponse:
    """统一响应包装。"""
    code: int = 0
    message: str = "ok"
    mock: bool = False
    data: Any = None
