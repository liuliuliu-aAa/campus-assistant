import React from "react";
import { Layout, Menu, Tag } from "antd";

const { Header, Content } = Layout;

const ITEMS = [
  { key: "dashboard", label: "仪表盘" },
  { key: "knowledge", label: "知识库" },
  { key: "qa", label: "智能问答" },
  { key: "detail", label: "资料详情" },
  { key: "monitor", label: "Agent 监控" },
  { key: "outline", label: "复习提纲" },
];

export default function AppLayout({ activeKey, onNavigate, children }) {
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          background: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 24px",
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 17 }}>
          校园资料智能整理助手
          <span style={{ color: "#8c96a8", fontSize: 12, marginLeft: 8 }}>七 Agent 协同</span>
        </div>
        <Tag color="green">MOCK</Tag>
      </Header>
      <Content style={{ padding: "0 24px 24px" }}>
        <Menu
          mode="horizontal"
          selectedKeys={[activeKey]}
          items={ITEMS}
          onClick={(event) => onNavigate(event.key)}
          style={{ marginBottom: 16 }}
        />
        {children}
      </Content>
    </Layout>
  );
}
