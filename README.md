# 校园资料智能整理助手（campus-assistant）

面向高校学生的校园资料智能整理助手：多 Agent 协同完成资料采集、分类、摘要、问答、提醒、校验与优化，全部能力在 **MOCK 模式零依赖** 下即可演示。

## 1. 项目定位与架构

七 Agent 协同，由编排层统一调度：

| Agent | 职责 |
| --- | --- |
| collector_agent | 多源渠道增量采集、按内容哈希去重 |
| classifier_agent | 三级分类（LLM → 向量校验 → 规则兜底），输出课程 / 章节 / 资料类型 / 重要等级 |
| summarizer_agent | PPT 逐页、PDF 分章节、图片 OCR 后摘要，输出摘要 / 知识点 / 关键词 / 场景 |
| qa_agent | RAG 问答，强制附来源，低置信与无结果显式声明 |
| reminder_agent | 截止 / 考试 / 活动识别，中文相对时间解析，多渠道推送 |
| validator_agent | L1–L5 五级校验，低置信转人工工单 |
| optimizer_agent | 消费降级消息与工单，输出八类优化建议 |

支撑模块：

- `orchestrator/`：TaskGraph（DAG 分批）、scheduler（`select_agent` 负载 + 响应时间选优）、executor（超时 / 指数退避重试 / 降级 / skipped）、message_bus（七字段消息，mock 内存实现）
- `services/`：rag_service、knowledge_graph、file_parser、notification
- `mcp/`：MCP 工具层（stdio JSON-RPC，工具复用上述 Agent）
- `app/main.py`：FastAPI 装配层；缺 FastAPI / pydantic 时自动降级为纯标准库 ASGI

## 2. 目录结构

```text
campus-assistant/
├── app/
│   ├── main.py                     # 装配层 + API 路由（FastAPI 缺失时降级 ASGI）
│   ├── config.py                   # mock / 真实双模式配置
│   ├── agents/
│   │   ├── base_agent.py           # AgentResult / BaseAgent
│   │   ├── collector_agent.py
│   │   ├── classifier_agent.py
│   │   ├── summarizer_agent.py
│   │   ├── qa_agent.py
│   │   ├── reminder_agent.py
│   │   ├── validator_agent.py
│   │   └── optimizer_agent.py
│   ├── orchestrator/
│   │   ├── task_graph.py           # TaskGraph / TaskNode / CycleDetectedError
│   │   ├── scheduler.py            # select_agent / NoAvailableAgentError
│   │   ├── executor.py             # TaskExecutor / TaskRecord
│   │   └── message_bus.py          # MessageBus / build_message / validate_message
│   ├── services/
│   │   ├── rag_service.py
│   │   ├── knowledge_graph.py      # 内存图谱，Neo4j 分支占位
│   │   ├── file_parser.py
│   │   └── notification.py
│   ├── mcp/
│   │   ├── mcp_server.py           # MCP 服务入口（stdio）
│   │   └── tools/
│   │       ├── common.py
│   │       ├── qa_tool.py
│   │       ├── summary_tool.py
│   │       ├── reminder_tool.py
│   │       └── validator_tool.py
│   ├── models/
│   │   └── api_models.py           # 请求 / 响应模型（pydantic 可选）
│   └── utils/
│       ├── logging_utils.py
│       ├── time_utils.py
│       └── hash_utils.py
├── frontend/                       # 前端演示（React + Ant Design + ECharts，全 mock）
│   ├── preview.html                # 无 Node：双击直开的静态预览入口（CDN + 内联 Babel）
│   ├── index.html                  # Vite 入口
│   ├── package.json
│   ├── vite.config.js
│   ├── api/
│   │   ├── client.js               # window.CampusAPI（preview.html 使用）
│   │   └── index.js                # ESM 版 api（React 源码使用）
│   ├── mock/
│   │   ├── data.js                 # window.MOCK_DATA，唯一 mock 数据源
│   │   └── index.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── components/             # AppLayout / LabelTags / MetricsCharts
│       └── pages/                  # 仪表盘 / 知识库 / 问答 / 资料详情 / Agent 监控 / 复习提纲
├── tests/                          # TC01–TC10
│   ├── conftest.py
│   ├── test_functional.py
│   ├── test_feedback.py
│   ├── test_performance.py
│   └── test_exception.py
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 3. 快速开始（MOCK，零外部依赖）

要求 Python 3.9+。MOCK 模式**零外部依赖即可演示**：不需要 API Key、Redis、向量库（Milvus / Qdrant）、Neo4j，也不需要 Node。可直接在外部终端执行 `py -3 -m pytest tests/ -v` 验证整条 mock 链路。

```bash
cd campus-assistant
# 可选：安装 Web 依赖（不装也能 import，启动 HTTP 服务则需要）
pip install fastapi uvicorn

# 启动（默认 MOCK_MODE=True）
python -m app.main
# 等价：uvicorn app.main:app --host 0.0.0.0 --port 8000
```

自检：

```bash
curl http://localhost:8000/api/health
curl -X POST http://localhost:8000/api/qa -H "Content-Type: application/json" -d "{\"query\":\"导数的定义是什么\"}"
```

> 说明：`main.py` 在导入时完成装配但不会启动服务；未安装 FastAPI 时 `app` 为纯标准库 ASGI 应用，可交给任意 ASGI 服务器运行。

## 4. 切换到真实模式

以 `app/config.py` 实际实现为准：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MOCK_MODE` | `true` | `false` 进入真实模式 |
| `LLM_API_KEY` | 空 | 真实模式必填；兼容 `DASHSCOPE_API_KEY` |
| `LLM_MODEL` | mock 下 `mock-qwen-max`；真实下 `qwen-max` | 通义千问模型名 |
| `VECTOR_DB_HOST` | `localhost:19530` | 向量库地址（按申报书以 Milvus 口径，端口 19530；MVP 未接真实向量库） |
| `REDIS_URL` | `redis://localhost:6379/0` | 任务队列 / 消息总线 |
| `MAX_RETRY` | `3` | 单任务重试次数（首次 + 3 次重试，共 4 次尝试） |
| `TASK_TIMEOUT` | `30` | 单任务超时（秒） |
| `NOTIFY_CHANNEL` | `inapp` | 推送渠道：`inapp` / `email` / `webhook` |

示例：

```bash
MOCK_MODE=false LLM_API_KEY=sk-xxx LLM_MODEL=qwen-max python -m app.main
```

真实模式的 LLM 调用、真实推送、真实解析库、Neo4j / 向量库接入目前均为 `NotImplementedError` 占位（见第 9 节）。

## 5. API 一览

所有响应统一包装：`{"code": 0, "message": "ok", "mock": true, "data": ...}`；错误时 `code` 与 HTTP 状态码一致（400 / 404 / 500 / 502），`data` 为 `null`。

| 方法 | 路径 | 说明 | 关键入参 |
| --- | --- | --- | --- |
| GET | `/api/health` | 健康检查与装配信息 | — |
| GET | `/api/agents/metrics` | 各 Agent total / success / fail 等指标 | — |
| POST | `/api/collect` | 采集 | `subscriptions` |
| POST | `/api/classify` | 分类 | `files` |
| POST | `/api/summarize` | 摘要 | `files` |
| POST | `/api/qa` | 问答 | `query` / `course` / `top_k` |
| POST | `/api/reminders` | 提醒提取 | `text` 或 `files` / `channel` |
| POST | `/api/validate` | 五级校验 | `outputs` 或 `classified` / `summaries` / `answer` / `sources` / `reminders` |
| POST | `/api/study-outline` | 复习提纲（summary + qa） | `files` / `query` / `course` / `top_k` |
| POST | `/api/pipeline` | 自动整理流水线 | `subscriptions` |

流水线 `collect → classify → summarize → validate` 由 `TaskGraph` 定依赖、`scheduler.select_agent` 选 Agent、`TaskExecutor` 执行（超时 / 重试 / 降级），`steps` 中返回每个阶段状态。

## 6. MCP 工具层

```bash
python -m app.mcp.mcp_server     # stdio JSON-RPC
```

支持 `initialize` / `tools/list` / `tools/call`，工具名：

- `ask_question`：`{"query", "course"?, "top_k"?}`
- `summarize_documents`：`{"files": [...]}`
- `extract_reminders`：`{"text"? , "files"?, "channel"?}`
- `validate_output`：`{"output": {...}}`

调用示例（单行 JSON 输入 stdin）：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

无 MCP SDK 时使用标准库实现；接入官方 SDK 时替换 `MCPServer.serve_stdio` 为 `stdio_server` 即可，工具定义可直接复用。

## 7. 前端演示（React + Ant Design + ECharts）

前端全部使用本地 mock 数据，不请求后端；所有数据访问都收敛在 `frontend/api/` 一层，后续接真实接口只改这一层（`USE_MOCK` / `BASE_URL`），页面代码不动。

### 7.1 无 Node：直接打开静态预览

双击 `campus-assistant/frontend/preview.html` 即可（浏览器 `file://` 打开）。React 18 / Ant Design 5 / ECharts 5 / Babel Standalone 全部通过 CDN 引入，**需要联网**，不需要 npm。

- API 层：`frontend/api/client.js`（`window.CampusAPI`，`USE_MOCK = true`）
- mock 数据：`frontend/mock/data.js`（`window.MOCK_DATA`）

`preview.html` 的 CDN 依赖（已固定版本，均实测返回 200）：

| 依赖 | 版本 | URL |
| --- | --- | --- |
| React | 18.3.1 | `https://unpkg.com/react@18.3.1/umd/react.production.min.js` |
| ReactDOM | 18.3.1 | `https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js` |
| dayjs（AntD 依赖） | 1.11.23 | `https://unpkg.com/dayjs@1.11.23/dayjs.min.js` |
| Ant Design | 5.29.3 | `https://unpkg.com/antd@5.29.3/dist/antd.min.js` |
| ECharts | 5.6.0 | `https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js` |
| Babel Standalone | 7.29.14 | `https://unpkg.com/@babel/standalone@7.29.14/babel.min.js` |

离线（无网络）表现：本地 `mock/data.js`、`api/client.js` 仍能加载，CDN 脚本失败后页面**不再白屏**——`preview.html` 已内置兜底：每个 CDN `<script>` 带 `onerror`、脚本加载后做全局依赖检查、`window.onerror` 捕获运行异常、8 秒未完成渲染则超时提示，统一显示静态提示块「前端资源加载失败」并给出具体原因（如“缺少依赖：React、ECharts”）。

### 7.2 有 Node：Vite 开发

```bash
cd campus-assistant/frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 dist/
```

- 入口：`frontend/index.html` → `frontend/src/main.jsx` → `src/App.jsx`
- API 层：`frontend/api/index.js`（ESM，`USE_MOCK = true`）
- mock 数据复用同一份 `frontend/mock/data.js`（通过 `index.html` 的 `<script src="/mock/data.js">` 注入）

### 7.3 页面与主线

| 页面 | 文件 | 内容 |
| --- | --- | --- |
| 仪表盘首页 | `src/pages/DashboardPage.jsx` | 健康状态、七 Agent 概览、整理流水线进度 |
| 知识库浏览 | `src/pages/KnowledgeBasePage.jsx` | 资料列表（课程 / 章节 / 类型 / 重要等级标签），点击进入详情 |
| 智能问答 | `src/pages/QaPage.jsx` | 提问 → 答案 + 来源 + 置信度 |
| 资料详情 | `src/pages/DocumentDetailPage.jsx` | 分段内容、摘要 / 知识点、校验记录 |
| Agent 监控面板 | `src/pages/AgentMonitorPage.jsx` | ECharts 成功/失败柱状图 + 占比饼图 + 指标明细表 |
| 复习提纲生成 | `src/pages/StudyOutlinePage.jsx` | 按章折叠的知识点提纲 + 来源表 |

切真实后端：把 `frontend/api/client.js`（预览）与 `frontend/api/index.js`（Vite）中的 `USE_MOCK` 改为 `false` 并配置 `BASE_URL`。

> 未验证项：本机未安装 Node，未执行 `npm install` / `npm run dev` / `npm run build`；`preview.html` 也未做浏览器渲染验证，仅保证文件已落盘与结构自洽。

## 8. 测试（TC01–TC10）

```bash
cd campus-assistant
py -3 -m pytest tests/ -v
```

| 用例 | 测试文件::函数 | 当前状态 |
| --- | --- | --- |
| TC01 PDF 课件分类 + 摘要 | `test_functional.py::test_tc01_pdf_classify_and_summarize` | 可跑（mock） |
| TC02 多格式解析 | `test_functional.py::test_tc02_multi_format_parse` | 可跑（mock） |
| TC03 自然语言问答 | `test_functional.py::test_tc03_natural_language_qa` | 可跑（mock） |
| TC04 跨文档问答 | `test_functional.py::test_tc04_cross_document_qa` | 可跑（mock，聚合能力待 RAG） |
| TC05 截止日期识别 | `test_functional.py::test_tc05_deadline_reminder` | 可跑（mock） |
| TC06 分类纠错反馈 | `test_feedback.py::test_tc06_classification_correction_feedback` | xfail：无纠错记录 / 相似文档修正实现 |
| TC07 高并发 | `test_performance.py::test_tc07_high_concurrency` | 可跑（只验证 100 并发不报错，不断言耗时） |
| TC08 检索性能 | `test_performance.py::test_tc08_retrieval_performance` | skip：<2s 为真实环境指标 |
| TC09 异常处理 | `test_exception.py::test_tc09_corrupted_file`、`test_tc09_executor_isolates_failed_task` | 可跑（mock；含 executor 单任务失败隔离断言） |
| TC10 复习提纲 | `test_functional.py::test_tc10_study_outline` | 可跑（mock） |

本机实测（`py -3 -m pytest tests/ -v`）：**9 passed, 1 skipped, 1 xfailed in 0.37s**（TC06 为 xfail、TC08 为 skip，属预期）。测试通过 `asyncio.run` 驱动，未依赖 pytest-asyncio。

TC09 的 `test_tc09_executor_isolates_failed_task` 断言：损坏/非法文件导致的异常被 `TaskExecutor` 包成 `degraded` 记录（带 `error`），同批次另一个正常任务仍 `succeeded`，依赖失败任务的下游任务标 `skipped`，整批不中断。

## 9. 已知限制

- 真实 LLM（通义千问 qwen-max）、Redis、向量库（Milvus / Qdrant）、Neo4j、邮件与 Webhook 推送均为 mock 或 `NotImplementedError` 占位：真实 LLM 调用、真实解析库（PyMuPDF / python-pptx / OCR）、Neo4j、向量库均未接入（MVP 为 mock，未接真实向量库，生产可替换 Milvus / Qdrant）；推送仅 `inapp` 为进程内记录，`email` / `webhook` 未实现。当前仅 MOCK 链路可完整演示。
- mock 摘要按标点切词拼装，不是真实语义摘要；mock 问答来源为内置示例来源。
- 采集游标与去重集合、通知记录均为进程内状态，重启后重置；`collector_agent` 中已标注 TODO 待持久化到元数据库。
- 消息总线真实模式仅预留 Redis 位置，mock 使用内存 asyncio 分发（未接入真实 Redis）。
- 纠错反馈（TC06）、10 万文档检索性能（TC08）尚无对应实现或真实环境。
- 前端预览依赖 CDN：`preview.html` 的 React / AntD / ECharts / Babel 全部走公网 CDN，离线时由内置兜底显示「前端资源加载失败」静态提示并附原因，不再整页空白；本机无 Node，`npm install` / `npm run dev` / `npm run build` 未执行，`preview.html` 未做浏览器渲染验证。

## 10. 部署

```bash
docker compose up --build
# 默认 MOCK 模式，访问 http://localhost:8000/api/health
```

compose 中附带可选 `redis` 服务，仅真实模式需要；mock 演示可忽略。向量库按申报书以 Milvus（默认 19530）口径标注，compose 内仅保留注释示例、未启用任何向量库镜像；文件不含顶层 `version` 字段（Compose Spec 已废弃该字段），编辑器若提示 schema 相关告警属提示性信息，不影响 `docker compose up`。
