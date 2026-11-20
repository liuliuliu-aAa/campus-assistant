import "../mock/index.js";

const USE_MOCK = true;
const BASE_URL = "";
const MOCK = () => window.MOCK_DATA;

function wrap(data) {
  return { code: 0, message: "ok", mock: USE_MOCK, data };
}

function delay(data, ms = 180) {
  return new Promise((resolve) => {
    setTimeout(() => resolve(wrap(JSON.parse(JSON.stringify(data)))), ms);
  });
}

async function request(path, options) {
  const response = await fetch(BASE_URL + path, options);
  return response.json();
}

function post(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

function mockSummary() {
  const data = MOCK();
  return {
    summaries: data.files.map((file) => ({
      document_id: file.document_id,
      original_filename: file.original_filename,
      file_type: file.file_type,
      segment_count: file.segments.length,
      ocr_applied: file.file_type === "image",
      ...file.summary,
    })),
    count: data.files.length,
  };
}

export const api = {
  useMock: USE_MOCK,
  health: () => (USE_MOCK ? delay(MOCK().health) : request("/api/health")),
  metrics: () => (USE_MOCK ? delay({ agents: MOCK().metrics }) : request("/api/agents/metrics")),
  pipeline: (payload) => (USE_MOCK ? delay(MOCK().pipeline, 600) : post("/api/pipeline", payload)),
  summarize: (payload) => (USE_MOCK ? delay(mockSummary()) : post("/api/summarize", payload)),
  ask: (payload) => (USE_MOCK ? delay(MOCK().qa) : post("/api/qa", payload)),
  validate: (payload) => (USE_MOCK ? delay(MOCK().validation) : post("/api/validate", payload)),
  outline: (payload) => (USE_MOCK ? delay(MOCK().outline, 400) : post("/api/study-outline", payload)),
};

export default api;
