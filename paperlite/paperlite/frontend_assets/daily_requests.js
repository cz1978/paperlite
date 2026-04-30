    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      if (!response.ok) {
        const fallback = `${response.status} ${response.statusText}`;
        let message = fallback;
        try {
          const raw = (await response.text()).trim();
          if (raw) {
            const contentType = response.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
              const payload = JSON.parse(raw);
              const detail = payload.detail || payload.error || payload.message;
              if (Array.isArray(detail)) {
                message = detail.map((item) => item.msg || item.message || JSON.stringify(item)).join("; ");
              } else if (detail && typeof detail === "object") {
                message = JSON.stringify(detail);
              } else if (detail) {
                message = String(detail);
              } else {
                message = raw;
              }
            } else {
              message = raw.slice(0, 500);
            }
          }
        } catch (_) {}
        const error = new Error(message);
        error.status = response.status;
        error.statusText = response.statusText;
        throw error;
      }
      return response.json();
    }
    function sleep(ms) {
      return new Promise((resolve) => window.setTimeout(resolve, ms));
    }
    function shouldRetryTranslate(error) {
      return error?.status === 429 || (error?.status >= 500 && error?.status < 600);
    }
    async function translatePaperWithThrottle(paper, style = "brief") {
      let attempt = 0;
      while (true) {
        try {
          return await fetchJson("/agent/translate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paper, target_language: "zh-CN", style }),
          });
        } catch (error) {
          attempt += 1;
          if (!shouldRetryTranslate(error) || attempt > TRANSLATE_MAX_RETRIES) throw error;
          const waitMs = TRANSLATE_RETRY_BASE_MS * Math.pow(2, attempt - 1);
          $("chainStatus").textContent = `LLM 限流/繁忙，${Math.round(waitMs / 1000)} 秒后重试 ${attempt}/${TRANSLATE_MAX_RETRIES}`;
          await sleep(waitMs);
        }
      }
    }
    function shouldRetryAiFilter(error) {
      return error?.status === 429 || (error?.status >= 500 && error?.status < 600);
    }
    async function filterPaperWithThrottle(paper, query, useProfile = true) {
      let attempt = 0;
      while (true) {
        try {
          return await fetchJson("/agent/filter", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ paper, query, use_profile: useProfile }),
          });
        } catch (error) {
          attempt += 1;
          if (!shouldRetryAiFilter(error) || attempt > AI_FILTER_MAX_RETRIES) throw error;
          const waitMs = AI_FILTER_RETRY_BASE_MS * Math.pow(2, attempt - 1);
          $("chainStatus").textContent = `AI 筛选限流/繁忙，${Math.round(waitMs / 1000)} 秒后重试 ${attempt}/${AI_FILTER_MAX_RETRIES}`;
          await sleep(waitMs);
        }
      }
    }
    async function indexRagScope(scope) {
      return fetchJson("/agent/rag/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scope),
      });
    }
    async function askRagScope(scope, question, topK) {
      return fetchJson("/agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...scope, question, top_k: topK }),
      });
    }
    async function fetchRelatedPapers(params) {
      return fetchJson(`/daily/related?${params.toString()}`);
    }
