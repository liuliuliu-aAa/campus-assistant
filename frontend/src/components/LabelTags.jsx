import React from "react";
import { Space, Tag } from "antd";

const DOC_TYPE_COLOR = { 课件: "blue", 习题: "purple", 笔记: "cyan", 通知: "gold", 试卷: "volcano" };

export function LabelTag({ name, label }) {
  const value = (label && label.label) || "未识别";
  const confidence = label && typeof label.confidence === "number" ? label.confidence : 0;
  return (
    <Tag color={confidence < 0.7 ? "orange" : DOC_TYPE_COLOR[value] || "geekblue"}>
      {name}：{value} {(confidence * 100).toFixed(0)}%
    </Tag>
  );
}

export default function LabelTags({ labels }) {
  const data = labels || {};
  return (
    <Space size={[4, 4]} wrap>
      <LabelTag name="课程" label={data.course} />
      <LabelTag name="章节" label={data.chapter} />
      <LabelTag name="类型" label={data.doc_type} />
      <LabelTag name="重要度" label={data.importance} />
    </Space>
  );
}
