import React, { useState } from "react";
import { Button, Card, Input, Progress, Space, Table, Typography } from "antd";
import api from "../../api/index.js";

const { Paragraph, Text } = Typography;

export default function QaPage() {
  const [query, setQuery] = useState("概率论中贝叶斯公式怎么应用");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  function ask() {
    if (!query.trim()) return;
    setLoading(true);
    api.ask({ query, top_k: 5 })
      .then((res) => setResult(res.data))
      .finally(() => setLoading(false));
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="智能问答（强制标注来源）">
        <Space.Compact style={{ width: "100%" }}>
          <Input value={query} onChange={(event) => setQuery(event.target.value)} onPressEnter={ask} />
          <Button type="primary" loading={loading} onClick={ask}>提问</Button>
        </Space.Compact>
      </Card>
      {result && (
        <Card title={"回答 · 置信度 " + result.confidence.toFixed(2)}>
          <Paragraph>{result.answer}</Paragraph>
          <Table
            rowKey="url"
            size="small"
            pagination={false}
            dataSource={result.sources}
            columns={[
              { title: "来源文档", dataIndex: "title" },
              { title: "链接", dataIndex: "url", render: (value) => <Text type="secondary">{value}</Text> },
              { title: "相关度", dataIndex: "score", width: 140, render: (value) => <Progress percent={Math.round(value * 100)} size="small" /> },
            ]}
          />
        </Card>
      )}
    </Space>
  );
}
