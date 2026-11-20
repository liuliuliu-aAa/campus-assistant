import React, { useState } from "react";
import { Alert, Button, Card, Collapse, Progress, Space, Table, Tag, Typography } from "antd";
import api from "../../api/index.js";
import { mockData } from "../../mock/index.js";

const { Paragraph, Text } = Typography;

export default function StudyOutlinePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  function generate() {
    setLoading(true);
    api.outline({ files: mockData.files, query: "数据结构期末复习提纲" })
      .then((res) => setData(res.data))
      .finally(() => setLoading(false));
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="复习提纲生成" extra={<Button type="primary" loading={loading} onClick={generate}>生成提纲</Button>}>
        <Text type="secondary">基于已整理资料的摘要与知识点，按章节聚合生成分层提纲（mock）。</Text>
      </Card>
      {data && (
        <>
          <Card title="提纲总览">
            <Alert type="success" showIcon message={data.summary} style={{ marginBottom: 12 }} />
            <Space size={[6, 6]} wrap>
              {data.knowledge_points.map((point) => <Tag color="blue" key={point}>{point}</Tag>)}
            </Space>
          </Card>
          <Card title="分章提纲">
            <Collapse
              items={data.chapters.map((chapter, index) => ({
                key: String(index),
                label: chapter.chapter,
                children: (
                  <div>
                    <Paragraph>{chapter.summary}</Paragraph>
                    <Space size={[6, 6]} wrap>
                      {chapter.points.map((point) => <Tag key={point}>{point}</Tag>)}
                    </Space>
                  </div>
                ),
              }))}
            />
          </Card>
          <Card title="来源">
            <Table
              rowKey="url"
              size="small"
              pagination={false}
              dataSource={data.sources}
              columns={[
                { title: "资料", dataIndex: "title" },
                { title: "链接", dataIndex: "url" },
                { title: "相关度", dataIndex: "score", width: 140, render: (value) => <Progress percent={Math.round(value * 100)} size="small" /> },
              ]}
            />
          </Card>
        </>
      )}
    </Space>
  );
}
