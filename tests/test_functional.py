"""TC01–TC05、TC10 功能测试（mock 模式，真调用已实现 Agent / services / 装配层）。"""

import asyncio

from app.agents.classifier_agent import ClassifierAgent
from app.agents.qa_agent import QAAgent
from app.agents.reminder_agent import ReminderAgent
from app.agents.summarizer_agent import SummarizerAgent
from app.services.file_parser import FileParser
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.notification import NotificationService


def run(coro):
    return asyncio.run(coro)


def make_task(agent_type, params):
    return {"task_id": "test-" + agent_type, "agent_type": agent_type, "params": params}


def test_tc01_pdf_classify_and_summarize():
    """TC01 PDF 课件上传与分类：线性代数 / 第三章 / 课件，并生成摘要。"""
    filename = "线性代数-第三章-课件.pdf"
    content = "第三章 矩阵的秩\n\n第三章 线性方程组的解\n\n矩阵的初等变换与秩的关系。"
    parsed = FileParser().parse({"original_filename": filename, "content": content})
    assert parsed["file_type"] == "pdf"
    assert parsed["segments"], "PDF 应至少解析出一个分段"

    classified = run(ClassifierAgent().run(make_task("classifier", {
        "files": [{"document_id": parsed["document_id"], "original_filename": filename,
                   "content": content}],
    })))
    assert classified.success
    labels = classified.data["classified"][0]["labels"]
    assert labels["course"]["label"] == "线性代数"
    assert labels["chapter"]["label"] == "第三章"
    assert labels["doc_type"]["label"] == "课件"

    summarized = run(SummarizerAgent().run(make_task("summarizer", {
        "files": [{"document_id": parsed["document_id"], "original_filename": filename,
                   "file_type": "pdf", "content": content}],
    })))
    assert summarized.success
    assert summarized.data["summaries"][0]["summary"]


def test_tc02_multi_format_parse():
    """TC02 多格式文件解析：PPT / Word / 图片 / PDF 均抽出文本且无乱码。"""
    cases = [
        ({"original_filename": "lecture.pptx", "content": "第一页 矩阵定义\n\n第二页 矩阵运算"}, "ppt"),
        ({"original_filename": "handout.pdf", "content": "第一章 概率论\n\n第二章 随机变量"}, "pdf"),
        ({"original_filename": "scan.png"}, "image"),
        ({"original_filename": "notes.docx", "content": "课堂笔记：贝叶斯公式推导"}, "text"),
    ]
    parser = FileParser()
    for document, expected_type in cases:
        parsed = parser.parse(document)
        assert parsed["file_type"] == expected_type
        assert parsed["segments"], "%s 应解析出文本" % document["original_filename"]
        texts = [segment["text"] for segment in parsed["segments"]]
        assert all(text.strip() for text in texts)
        assert all("\ufffd" not in text for text in texts), "解析结果不应出现乱码替换符"


def test_tc03_natural_language_qa():
    """TC03 自然语言问答：返回回答并附带来源文档（title/url/score）。"""
    result = run(QAAgent(knowledge_graph=KnowledgeGraphService()).run(make_task("qa", {
        "query": "概率论中贝叶斯公式怎么应用",
    })))
    assert result.success
    data = result.data
    assert data["answer"]
    assert data["sources"], "答案必须附带来源列表"
    for source in data["sources"]:
        assert {"title", "url", "score"} <= set(source)
    assert 0.0 <= data["confidence"] <= 1.0


def test_tc04_cross_document_qa():
    """TC04 跨文档综合问答：mock 下校验聚合回答结构（真实多课程聚合待 RAG 接入）。"""
    result = run(QAAgent(knowledge_graph=KnowledgeGraphService()).run(make_task("qa", {
        "query": "总结本学期所有课程的重点",
    })))
    assert result.success
    assert result.data["answer"]
    assert isinstance(result.data["sources"], list)


def test_tc05_deadline_reminder():
    """TC05 截止日期识别：作业 11 月 30 日截止 → deadline 提醒且日期可解析。"""
    result = run(ReminderAgent(notification=NotificationService()).run(make_task("reminder", {
        "text": "通知：作业11月30日截止，请按时提交。",
    })))
    assert result.success
    deadlines = [item for item in result.data["reminders"] if item["event_type"] == "deadline"]
    assert deadlines, "应识别出 deadline 事件"
    reminder = deadlines[0]
    assert reminder["due_date"] and reminder["due_date"].endswith("-11-30")
    assert reminder["status"] in ("pending", "pushed")


def test_tc10_study_outline():
    """TC10 复习提纲：多章节资料生成摘要 + 提纲，覆盖全部输入文档。"""
    from app.main import AppContainer

    files = [
        {"document_id": "doc_ch1", "original_filename": "数据结构-第一章.pdf",
         "file_type": "pdf", "content": "第一章 绪论\n\n算法的复杂度分析。"},
        {"document_id": "doc_ch2", "original_filename": "数据结构-第二章.pdf",
         "file_type": "pdf", "content": "第二章 线性表\n\n顺序表与链表。"},
    ]
    data = run(AppContainer().study_outline({"files": files}))
    assert "summary" in data and "qa" in data
    summaries = data["summary"]["summaries"]
    assert len(summaries) == len(files)
    assert all(item.get("summary") for item in summaries)
    assert isinstance(data["knowledge_points"], list)
