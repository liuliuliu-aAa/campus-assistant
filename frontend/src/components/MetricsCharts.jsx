import React, { useEffect, useRef } from "react";
import { Card, Col, Row } from "antd";
import * as echarts from "echarts";

export default function MetricsCharts({ metrics }) {
  const barRef = useRef(null);
  const pieRef = useRef(null);

  useEffect(() => {
    if (!barRef.current) return undefined;
    const chart = echarts.init(barRef.current);
    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["成功", "失败"], top: 0 },
      grid: { left: 40, right: 20, top: 40, bottom: 30 },
      xAxis: { type: "category", data: metrics.map((item) => item.agent), axisLabel: { rotate: 20 } },
      yAxis: { type: "value" },
      series: [
        { name: "成功", type: "bar", stack: "total", itemStyle: { color: "#52c41a" }, data: metrics.map((item) => item.success) },
        { name: "失败", type: "bar", stack: "total", itemStyle: { color: "#ff4d4f" }, data: metrics.map((item) => item.fail) },
      ],
    });
    return () => chart.dispose();
  }, [metrics]);

  useEffect(() => {
    if (!pieRef.current) return undefined;
    const chart = echarts.init(pieRef.current);
    const success = metrics.reduce((sum, item) => sum + item.success, 0);
    const fail = metrics.reduce((sum, item) => sum + item.fail, 0);
    chart.setOption({
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [{
        type: "pie",
        radius: ["45%", "70%"],
        data: [
          { name: "成功", value: success, itemStyle: { color: "#52c41a" } },
          { name: "失败", value: fail, itemStyle: { color: "#ff4d4f" } },
        ],
        label: { formatter: "{b}: {c} ({d}%)" },
      }],
    });
    return () => chart.dispose();
  }, [metrics]);

  return (
    <Row gutter={16}>
      <Col span={14}><Card title="各 Agent 成功 / 失败任务数"><div ref={barRef} style={{ height: 320 }} /></Card></Col>
      <Col span={10}><Card title="任务结果占比"><div ref={pieRef} style={{ height: 320 }} /></Card></Col>
    </Row>
  );
}
