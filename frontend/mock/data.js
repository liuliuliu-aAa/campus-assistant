/* 本地 mock 数据：preview.html（classic script）与 Vite 源码共用，字段与后端 /api/* 保持一致。 */
window.MOCK_DATA = {
  health: {
    status: "ok",
    mock_mode: true,
    fastapi_available: true,
    agents: ["collector", "classifier", "summarizer", "qa", "reminder", "validator", "optimizer"],
    tools: ["ask_question", "summarize_documents", "extract_reminders", "validate_output"],
  },

  agentsInfo: [
    { key: "collector", name: "采集 Agent", duty: "多源增量采集 · 内容哈希去重" },
    { key: "classifier", name: "分类 Agent", duty: "LLM → 向量校验 → 规则兜底" },
    { key: "summarizer", name: "摘要 Agent", duty: "PPT 逐页 / PDF 分章 / 图片 OCR" },
    { key: "qa", name: "问答 Agent", duty: "RAG 检索 · 强制附来源" },
    { key: "reminder", name: "提醒 Agent", duty: "截止 / 考试 / 活动 · 中文相对时间" },
    { key: "validator", name: "校验 Agent", duty: "L1–L5 五级校验 · 转人工工单" },
    { key: "optimizer", name: "优化 Agent", duty: "降级消息与工单 → 策略优化建议" },
  ],

  metrics: [
    { agent: "collector", total: 12, success: 12, fail: 0, current_load: 0, avg_response_time: 0.42 },
    { agent: "classifier", total: 30, success: 29, fail: 1, current_load: 1, avg_response_time: 0.21 },
    { agent: "summarizer", total: 18, success: 17, fail: 1, current_load: 0, avg_response_time: 0.55 },
    { agent: "qa", total: 41, success: 40, fail: 1, current_load: 0, avg_response_time: 0.33 },
    { agent: "reminder", total: 9, success: 9, fail: 0, current_load: 0, avg_response_time: 0.08 },
    { agent: "validator", total: 24, success: 22, fail: 2, current_load: 0, avg_response_time: 0.12 },
    { agent: "optimizer", total: 4, success: 4, fail: 0, current_load: 0, avg_response_time: 0.05 },
  ],

  files: [
    {
      document_id: "doc_ch03",
      original_filename: "线性代数-第三章-课件.pdf",
      channel: "course_group", uploader: "李同学", file_type: "pdf",
      labels: {
        course: { label: "线性代数", confidence: 0.92 },
        chapter: { label: "第三章", confidence: 0.88 },
        doc_type: { label: "课件", confidence: 0.95 },
        importance: { label: "高", confidence: 0.81 },
      },
      segments: [
        { seq: 1, source: "chapter:1", text: "第三章 矩阵的秩：秩的定义、初等变换不改变秩。" },
        { seq: 2, source: "chapter:2", text: "线性方程组有解判定与基础解系的求法。" },
      ],
      summary: {
        summary: "本章讲解矩阵的秩及其与线性方程组解的关系。",
        knowledge_points: ["矩阵的秩", "初等变换", "有解判定", "基础解系"],
        keywords: ["矩阵", "秩", "线性方程组", "初等变换"],
        scenario: "期末复习 · 习题讲解",
        truncated: false,
      },
    },
    {
      document_id: "doc_prob02",
      original_filename: "概率论-第二章-习题.docx",
      channel: "lms", uploader: "王同学", file_type: "text",
      labels: {
        course: { label: "概率论", confidence: 0.9 },
        chapter: { label: "第二章", confidence: 0.72 },
        doc_type: { label: "习题", confidence: 0.87 },
        importance: { label: "中", confidence: 0.44 },
      },
      segments: [
        { seq: 1, source: "paragraph:1", text: "第二章 随机变量：离散型与连续型分布。" },
        { seq: 2, source: "paragraph:2", text: "贝叶斯公式练习题：先验、似然与后验。" },
      ],
      summary: {
        summary: "第二章覆盖随机变量与贝叶斯公式的典型习题。",
        knowledge_points: ["随机变量", "贝叶斯公式", "条件概率"],
        keywords: ["随机变量", "贝叶斯", "条件概率"],
        scenario: "课后练习 · 考前自测",
        truncated: false,
      },
    },
    {
      document_id: "doc_ds04",
      original_filename: "数据结构-第四章-扫描件.png",
      channel: "mail", uploader: "赵同学", file_type: "image",
      labels: {
        course: { label: "数据结构", confidence: 0.66 },
        chapter: { label: "第四章", confidence: 0.61 },
        doc_type: { label: "课件", confidence: 0.58 },
        importance: { label: "中", confidence: 0.5 },
      },
      segments: [
        { seq: 1, source: "ocr", text: "OCR 模拟识别：树与二叉树、遍历方式、二叉搜索树。" },
      ],
      summary: {
        summary: "扫描件内容为树与二叉树的基本概念与遍历。",
        knowledge_points: ["二叉树", "树的遍历", "二叉搜索树"],
        keywords: ["树", "二叉树", "遍历"],
        scenario: "课堂补充 · 概念梳理",
        truncated: false,
      },
    },
  ],

  pipeline: {
    steps: [
      { stage: "collect", state: "succeeded", attempts: 1, execution_time: 0.12, confidence: 1.0 },
      { stage: "classify", state: "succeeded", attempts: 1, execution_time: 0.21, confidence: 0.88 },
      { stage: "summarize", state: "succeeded", attempts: 1, execution_time: 0.34, confidence: 0.9 },
      { stage: "validate", state: "succeeded", attempts: 1, execution_time: 0.12, confidence: 0.86 },
    ],
  },

  qa: {
    answer: "贝叶斯公式用于由先验概率与似然更新后验概率：先划分样本空间，写出条件概率，再代入公式计算。",
    sources: [
      { title: "概率论-第二章-课件.pdf", url: "mock://docs/prob-02", score: 0.91 },
      { title: "概率论-第二章-习题.docx", url: "mock://docs/prob-02-ex", score: 0.84 },
      { title: "概率论复习提纲（知识点）", url: "mock://kg/prob-bayes", score: 0.78 },
    ],
    confidence: 0.84,
  },

  validation: {
    validated: [
      { level: "L1", kind: "classification", target: "doc_ch03", result: "pass", issue: "", confidence: 0.92 },
      { level: "L2", kind: "summary", target: "doc_ch03", result: "pass", issue: "", confidence: 0.9 },
      { level: "L3", kind: "qa", target: "qa-001", result: "review", issue: "答案置信度与来源均分偏差超过 0.1", confidence: 0.72 },
      { level: "L4", kind: "qa", target: "qa-001", result: "pass", issue: "", confidence: 0.84 },
      { level: "L5", kind: "reminder", target: "rem-003", result: "review", issue: "时间未解析，需人工确认", confidence: 0.4 },
    ],
    passed: 2, failed: 0, needs_review: 2,
    tickets: [
      { ticket_id: "RV-8F2A11C0", level: "L3", kind: "qa", issue: "答案置信度与来源均分偏差超过 0.1", status: "open" },
      { ticket_id: "RV-31B7D902", level: "L5", kind: "reminder", issue: "时间未解析，需人工确认", status: "open" },
    ],
  },

  outline: {
    chapters: [
      { chapter: "第三章 矩阵的秩", points: ["秩的定义", "初等变换", "有解判定", "基础解系"], summary: "掌握秩的计算与线性方程组解的判定。" },
      { chapter: "第二章 随机变量", points: ["离散型分布", "连续型分布", "贝叶斯公式"], summary: "理解随机变量与条件概率的典型应用。" },
    ],
    knowledge_points: ["矩阵的秩", "初等变换", "有解判定", "基础解系", "随机变量", "贝叶斯公式"],
    summary: "按课程与章节聚合重点，建议先复习秩与方程组，再练习贝叶斯公式。",
    sources: [
      { title: "线性代数-第三章-课件.pdf", url: "mock://docs/la-03", score: 0.9 },
      { title: "概率论-第二章-习题.docx", url: "mock://docs/prob-02", score: 0.83 },
    ],
  },
};
