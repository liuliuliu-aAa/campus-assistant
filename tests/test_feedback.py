"""TC06 分类纠错反馈（当前能力缺失，标记 xfail）。"""

import pytest


@pytest.mark.xfail(reason="当前未实现纠错记录与相似文档自动修正能力", strict=False)
def test_tc06_classification_correction_feedback():
    """TC06：用户拖拽纠错 → 记录纠错并对相似文档自动修正（能力未实现）。"""
    from app.main import AppContainer

    container = AppContainer()
    # 期望存在的纠错接口；当前不存在，触发 AttributeError 即标记 xfail
    container.record_correction("doc_001", {"course": "线性代数", "chapter": "第三章"})
