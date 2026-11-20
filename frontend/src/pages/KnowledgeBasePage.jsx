import React from "react";
import { Button, Card, Table, Typography } from "antd";
import LabelTags from "../components/LabelTags.jsx";
import { mockData } from "../../mock/index.js";

const { Text } = Typography;

export default function KnowledgeBasePage({ onOpenDocument }) {
  const columns = [
    {
      title: "文件",
      dataIndex: "original_filename",
      render: (value, record) => (
        <a onClick={() => onOpenDocument(record)} style={{ fontWeight: 600 }}>{value}</a>
      ),
    },
    { title: "渠道", dataIndex: "channel", width: 130 },
    { title: "上传者", dataIndex: "uploader", width: 100 },
    { title: "分类结果", render: (_, record) => <LabelTags labels={record.labels} /> },
    {
      title: "操作",
      width: 100,
      render: (_, record) => <Button size="small" onClick={() => onOpenDocument(record)}>详情</Button>,
    },
  ];

  return (
    <Card title={"知识库 · 共 " + mockData.files.length + " 份资料"} extra={<Text type="secondary">点击文件名查看详情</Text>}>
      <Table rowKey="document_id" size="small" pagination={false} dataSource={mockData.files} columns={columns} />
    </Card>
  );
}
