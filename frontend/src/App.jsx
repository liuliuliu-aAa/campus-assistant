import React, { useState } from "react";
import AppLayout from "./components/AppLayout.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import KnowledgeBasePage from "./pages/KnowledgeBasePage.jsx";
import QaPage from "./pages/QaPage.jsx";
import DocumentDetailPage from "./pages/DocumentDetailPage.jsx";
import AgentMonitorPage from "./pages/AgentMonitorPage.jsx";
import StudyOutlinePage from "./pages/StudyOutlinePage.jsx";

export default function App() {
  const [activeKey, setActiveKey] = useState("dashboard");
  const [currentFile, setCurrentFile] = useState(null);

  function openDocument(file) {
    setCurrentFile(file);
    setActiveKey("detail");
  }

  function navigate(key) {
    if (key !== "detail") setCurrentFile(null);
    setActiveKey(key);
  }

  const pages = {
    dashboard: <DashboardPage onNavigate={navigate} />,
    knowledge: <KnowledgeBasePage onOpenDocument={openDocument} />,
    qa: <QaPage />,
    detail: <DocumentDetailPage file={currentFile} onBack={() => navigate("knowledge")} />,
    monitor: <AgentMonitorPage />,
    outline: <StudyOutlinePage />,
  };

  return (
    <AppLayout activeKey={activeKey} onNavigate={navigate}>
      {pages[activeKey]}
    </AppLayout>
  );
}
