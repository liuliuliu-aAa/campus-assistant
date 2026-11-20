"""pytest 基础配置：注入项目根路径并确保测试运行在 mock 模式。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("MOCK_MODE", "true")
