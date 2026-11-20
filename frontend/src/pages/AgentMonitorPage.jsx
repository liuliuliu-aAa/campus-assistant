import React, { useEffect, useState } from "react";
import { Card, Space, Table } from "antd";
import MetricsCharts from "../components/MetricsCharts.jsx";
import api from "../../api/index.js";
import { mockData } from "../../mock/index.js";

export default function AgentMonitorPage() {
  const [metrics, setMetrics] = useState(mockData.metrics);

  useEffect(() => {
    api.metrics().then((res) => setMetrics(res.data.agents));
  }, []);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <MetricsCharts metrics={metrics} />
      <Card title="Agent 指标明细">
        <Table
          rowKey="agent"
          size="small"
          pagination={false}
          dataSource={metrics}
          columns={[
            { title: "Agent", dataIndex: "agent" },
            { title: "总任务", dataIndex: "total", width: 100 },
            { title: "成功", dataIndex: "success", width: 100 },
            { title: "失败", dataIndex: "fail", width: 100 },
            { title: "当前负载", dataIndex: "current_load", width: 110 },
            { title: "平均响应(s)", dataIndex: "avg_response_time", width: 130 },
          ]}
        />
      </Card>
    </Space>
  );
}
