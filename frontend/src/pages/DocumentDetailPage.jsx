import React, { useEffect, useState } from "react";
import { Button, Card, Descriptions, Divider, Empty, Space, Table, Tag, Typography } from "antd";
import LabelTags from "../components/LabelTags.jsx";
import api from "../../api/index.js";
import { mockData } from "../../mock/index.js";

const { Paragraph, Text } = Typography;
const RESULT_COLOR = { pass: "green", fail: "red", review: "orange", skip: "default" };

export default function DocumentDetailPage({ file, onBack }) {
  const [summary, setSummary] = useState(file ? file.summary : null);

  useEffect(() => {
    if (!file) return;
    setSummary(file.summary);
    api.summarize({ files: [file] }).then((res) => setSummary(res.data.summaries[0]));
  }, [file && file.document_id]);

  if (!file) {
    return <Empty description="请从知识库选择一份资料" />;
  }

  const checks = mockData.validation.validated.filter((item) => item.target === file.document_id);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        title={<Space><Button size="small" onClick={onBack}>返回</Button>{file.original_filename}</Space>}
        extra={<Tag color="blue">{file.file_type}</Tag>}
      >
        <Descriptions column={3} size="small">
          <Descriptions.Item label="来源渠道">{file.channel}</Descriptions.Item>
          <Descriptions.Item label="上传者">{file.uploader}</Descriptions.Item>
          <Descriptions.Item label="文档 ID">{file.document_id}</Descriptions.Item>
        </Descriptions>
        <Divider />
        <LabelTags labels={file.labels} />
      </Card>
      <Card title="解析分段">
        <Table
          rowKey="seq"
          size="small"
          pagination={false}
          dataSource={file.segments}
          columns={[
            { title: "#", dataIndex: "seq", width: 60 },
            { title: "来源", dataIndex: "source", width: 140 },
            { title: "文本", dataIndex: "text" },
          ]}
        />
      </Card>
      {summary && (
        <Card title="摘要">
          <Paragraph>{summary.summary}</Paragraph>
          <Descriptions column={2} size="small" style={{ marginBottom: 8 }}>
            <Descriptions.Item label="适用场景">{summary.scenario}</Descriptions.Item>
            <Descriptions.Item label="是否截断">{summary.truncated ? "是（内容不完整）" : "否"}</Descriptions.Item>
          </Descriptions>
          <Space size={[6, 6]} wrap>
            {summary.knowledge_points.map((point) => <Tag color="blue" key={point}>{point}</Tag>)}
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">关键词：</Text>
            {summary.keywords.map((keyword) => <Tag key={keyword}>{keyword}</Tag>)}
          </div>
        </Card>
      )}
      <Card title="校验记录（该文档）">
        {checks.length === 0 ? <Empty description="暂无校验记录" /> : (
          <Table
            rowKey={(record) => record.level + record.target}
            size="small"
            pagination={false}
            dataSource={checks}
            columns={[
              { title: "级别", dataIndex: "level", width: 80 },
              { title: "结果", dataIndex: "result", width: 100, render: (value) => <Tag color={RESULT_COLOR[value]}>{value}</Tag> },
              { title: "问题", dataIndex: "issue", render: (value) => value || "—" },
              { title: "置信度", dataIndex: "confidence", width: 100, render: (value) => (value * 100).toFixed(0) + "%" },
            ]}
          />
        )}
      </Card>
    </Space>
  );
}
