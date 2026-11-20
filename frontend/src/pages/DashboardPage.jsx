import React, { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Col, Row, Space, Statistic } from "antd";
import api from "../../api/index.js";
import { mockData } from "../../mock/index.js";

export default function DashboardPage({ onNavigate }) {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    api.health().then((res) => setHealth(res.data));
  }, []);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Row gutter={16}>
          <Col span={6}><Statistic title="服务状态" value={health ? health.status : "..."} valueStyle={{ color: "#52c41a" }} /></Col>
          <Col span={6}><Statistic title="运行模式" value={health && health.mock_mode ? "MOCK" : "REAL"} /></Col>
          <Col span={6}><Statistic title="已装配 Agent" value={health ? health.agents.length : 0} /></Col>
          <Col span={6}><Statistic title="MCP 工具" value={health ? health.tools.length : 0} /></Col>
        </Row>
      </Card>
      <Alert type="info" showIcon message="当前为本地 mock 数据，不请求后端；API 调用集中在 api/index.js，切换真实接口只需改 USE_MOCK 与 BASE_URL。" />
      <Card title="七 Agent 协同">
        <Row gutter={[16, 16]}>
          {mockData.agentsInfo.map((agent) => (
            <Col span={8} key={agent.key}>
              <Card size="small" title={<Space><Badge status="processing" />{agent.name}</Space>}>
                <span style={{ color: "#8c96a8" }}>{agent.duty}</span>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>
      <Card title="快速入口">
        <Space>
          <Button type="primary" onClick={() => onNavigate("knowledge")}>浏览知识库</Button>
          <Button onClick={() => onNavigate("qa")}>智能问答</Button>
          <Button onClick={() => onNavigate("monitor")}>Agent 监控</Button>
        </Space>
      </Card>
    </Space>
  );
}
