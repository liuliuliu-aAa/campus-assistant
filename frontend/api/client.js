/* API 调用封装层：USE_MOCK=true 全走本地 mock；切真实后端只改 USE_MOCK / BASE_URL。 */
window.CampusAPI = (function () {
  const USE_MOCK = true;
  const BASE_URL = "";
  const MOCK = window.MOCK_DATA;

  function wrap(data) {
    return { code: 0, message: "ok", mock: USE_MOCK, data: data };
  }

  function delay(data, ms) {
    return new Promise(function (resolve) {
      setTimeout(function () { resolve(wrap(JSON.parse(JSON.stringify(data)))); }, ms || 180);
    });
  }

  function request(path, options) {
    return fetch(BASE_URL + path, options).then(function (response) {
      return response.json();
    });
  }

  function post(path, payload) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  }

  return {
    useMock: USE_MOCK,
    health: function () {
      return USE_MOCK ? delay(MOCK.health) : request("/api/health");
    },
    metrics: function () {
      return USE_MOCK ? delay({ agents: MOCK.metrics }) : request("/api/agents/metrics");
    },
    pipeline: function (payload) {
      return USE_MOCK ? delay(MOCK.pipeline, 600) : post("/api/pipeline", payload);
    },
    summarize: function (payload) {
      return USE_MOCK ? delay({ summaries: MOCK.files.map(function (f) { return Object.assign({ document_id: f.document_id, original_filename: f.original_filename, file_type: f.file_type, segment_count: f.segments.length, ocr_applied: f.file_type === "image" }, f.summary); }), count: MOCK.files.length }) : post("/api/summarize", payload);
    },
    ask: function (payload) {
      return USE_MOCK ? delay(MOCK.qa) : post("/api/qa", payload);
    },
    validate: function (payload) {
      return USE_MOCK ? delay(MOCK.validation) : post("/api/validate", payload);
    },
    outline: function (payload) {
      return USE_MOCK ? delay(MOCK.outline, 400) : post("/api/study-outline", payload);
    },
  };
})();
