    function syncUrl(q) {
      const url = new URL(window.location.href);
      url.searchParams.set("date_from", $("dateFrom").value);
      url.searchParams.set("date_to", $("dateTo").value);
      url.searchParams.set("page", String(state.page));
      if (q) url.searchParams.set("q", q); else url.searchParams.delete("q");
      if (state.selectedDiscipline) url.searchParams.set("discipline", state.selectedDiscipline); else url.searchParams.delete("discipline");
      if (state.selectedSources.size) url.searchParams.set("source", Array.from(state.selectedSources).join(",")); else url.searchParams.delete("source");
      history.replaceState(null, "", url);
    }
    async function loadPapers(actionLabel) {
      state.viewMode = "daily";
      updateButtons();
      $("resultStatus").textContent = actionLabel ? `${actionLabel}中...` : "正在加载...";
      $("chainStatus").textContent = actionLabel ? `${actionLabel}：准备读取缓存` : "自动：准备读取缓存";
      const offset = (state.page - 1) * PAGE_SIZE;
      const q = $("search").value.trim();
      const limitPerSource = q ? 500 : Math.min(500, offset + PAGE_SIZE + 1);
      try {
        const dayCount = dateRangeDayCount($("dateFrom").value, $("dateTo").value);
        if (!dayCount) throw new Error("invalid date range");
        const requestMode = actionLabel ? "手动" : "自动";
        const sourceDescription = effectiveSourceDescription(Array.from(state.selectedSources));
        const payload = await fetchJson(`/daily/cache?${cacheParams($("dateFrom").value, $("dateTo").value, limitPerSource).toString()}`);
        const all = flattenDailyPayloads([payload], q);
        state.allItems = all;
        clearAiFilterState();
        clearRelatedState();
        state.ragResult = null;
        renderRagResult();
        await syncLibraryState(state.allItems);
        const activeSources = Array.from(state.sourceCounts.values()).filter((count) => count > 0).length;
        $("chainStatus").textContent = `${requestMode}：/daily/cache · ${dayCount} 天 · ${sourceDescription}`;
        renderVisibleItems(activeSources);
      } catch (error) {
        state.sourceCounts = new Map();
        state.hasMore = false;
        state.currentItems = [];
        state.allItems = [];
        clearRelatedState();
        state.ragResult = null;
        renderRagResult();
        state.viewMode = "daily";
        $("resultStatus").textContent = "加载失败";
        $("chainStatus").textContent = "读取链路：/daily/cache 失败，未请求外部源";
        $("paperList").innerHTML = `<div class="empty">加载失败：${escapeHtml(error.message)}</div>`;
      }
      updateButtons();
      if ($("sourcePopover").classList.contains("open")) renderSourcePicker();
      syncUrl(q);
    }
    function targetBatchPapers() {
      const selected = (state.allItems || []).filter((paper) => state.selectedKeys.has(paperReadingKey(paper)));
      return selected.length ? selected : (state.currentItems || []);
    }
    function boundedNumberInput(id, fallback, min, max) {
      const value = Number($(id).value);
      if (!Number.isFinite(value)) return fallback;
      return Math.max(min, Math.min(max, Math.round(value)));
    }
    function clearRelatedState() {
      state.relatedPapers = new Map();
      state.relatedInFlightIds = new Set();
    }
    function relatedScopeParams(paper) {
      const params = new URLSearchParams();
      params.set("paper_id", paper.id);
      params.set("date_from", $("dateFrom").value);
      params.set("date_to", $("dateTo").value);
      params.set("top_k", "5");
      params.set("limit_per_source", "500");
      const q = $("search").value.trim();
      if (q) params.set("q", q);
      if (state.selectedDiscipline) params.set("discipline", state.selectedDiscipline);
      if (state.selectedSources.size) params.set("source", Array.from(state.selectedSources).join(","));
      return params;
    }
    async function loadRelatedPapers(paper) {
      if (!paper?.id) return;
      if (state.relatedInFlightIds.has(paper.id)) return;
      const existing = state.relatedPapers.get(paper.id);
      if (existing && existing.status === "done") return;
      state.relatedInFlightIds.add(paper.id);
      state.relatedPapers.set(paper.id, { status: "loading", payload: null, error: "" });
      renderPapers(state.currentItems);
      try {
        const payload = await fetchRelatedPapers(relatedScopeParams(paper));
        state.relatedPapers.set(paper.id, { status: "done", payload, error: "" });
      } catch (error) {
        state.relatedPapers.set(paper.id, { status: "error", payload: null, error: error.message });
      } finally {
        state.relatedInFlightIds.delete(paper.id);
        renderPapers(state.currentItems);
      }
    }
    function ragScopePayload() {
      const payload = {
        date_from: $("dateFrom").value,
        date_to: $("dateTo").value,
        limit_per_source: 500,
      };
      const q = $("search").value.trim();
      if (q) payload.q = q;
      if (state.selectedDiscipline) payload.discipline = state.selectedDiscipline;
      if (state.selectedSources.size) payload.source = Array.from(state.selectedSources).join(",");
      return payload;
    }
    function ragScopeLabel(scope) {
      const source = scope.source ? `来源 ${scope.source}` : "全部来源";
      const discipline = scope.discipline ? `学科 ${scope.discipline}` : "全部学科";
      const q = scope.q ? `搜索 ${scope.q}` : "无搜索词";
      return `${scope.date_from || ""} 至 ${scope.date_to || ""} · ${discipline} · ${source} · ${q}`;
    }
    function ragWarnings(warnings) {
      const items = (warnings || []).filter(Boolean);
      if (!items.length) return "";
      return `<div class="rag-warnings">Warnings: ${items.map((item) => escapeHtml(item)).join(" / ")}</div>`;
    }
    function ragRetrievalSummary(retrieval) {
      if (!retrieval) return "";
      const parts = [
        `候选 ${retrieval.candidates ?? 0}`,
        `已索引 ${retrieval.indexed ?? 0}`,
        `过期 ${retrieval.stale ?? 0}`,
        `命中 ${retrieval.matches ?? 0}`,
      ];
      return `<div class="rag-meta">${parts.map(escapeHtml).join(" · ")}</div>`;
    }
    function ragCitationLink(paper) {
      const links = [];
      if (paper.url) links.push(externalLink(paper.url, "URL"));
      if (paper.doi) links.push(externalLink(`https://doi.org/${paper.doi}`, "DOI"));
      if (paper.openalex_id) links.push(externalLink(paper.openalex_id, "OpenAlex"));
      return links.filter(Boolean).join(" · ");
    }
    function renderRagCitation(citation) {
      const paper = citation.paper || {};
      const authors = Array.isArray(paper.authors) ? paper.authors.slice(0, 6).join(", ") : "";
      const categories = Array.isArray(paper.categories) ? paper.categories.slice(0, 6).join(", ") : "";
      const score = Number.isFinite(Number(citation.score)) ? Number(citation.score).toFixed(3) : "";
      const link = ragCitationLink(paper);
      return `
        <article class="rag-citation">
          <div class="rag-citation-head">
            <span>[${escapeHtml(citation.index || "")}] ${escapeHtml(paper.title || "Untitled")}</span>
            <span>${score ? `score ${escapeHtml(score)}` : ""}</span>
          </div>
          <div class="rag-citation-meta">
            ${escapeHtml([paper.source, paper.venue || paper.journal, paper.published_at].filter(Boolean).join(" · "))}
          </div>
          <div class="rag-citation-meta">${escapeHtml(authors)}</div>
          ${categories ? `<div class="rag-citation-meta">${escapeHtml(categories)}</div>` : ""}
          ${paper.abstract ? `<p>${escapeHtml(String(paper.abstract).slice(0, 420))}</p>` : ""}
          ${link ? `<div class="rag-citation-links">${link}</div>` : ""}
        </article>
      `;
    }
    function renderRagResult() {
      const panel = $("ragResultPanel");
      const result = state.ragResult;
      if (!result) {
        panel.classList.remove("show");
        panel.innerHTML = "";
        return;
      }
      const payload = result.payload || {};
      const scope = ragScopeLabel(result.type === "ask" ? (payload.retrieval || payload) : payload);
      if (result.type === "index") {
        const summary = [
          `候选 ${payload.candidates ?? 0}`,
          `新建/刷新 ${payload.indexed ?? 0}`,
          `跳过 ${payload.skipped ?? 0}`,
          `embedding ${payload.embedding_model || "未配置"}`,
        ].join(" · ");
        panel.innerHTML = `
          <div class="rag-result-head">
            <strong>RAG索引</strong>
            <span>${escapeHtml(scope)}</span>
          </div>
          <div class="rag-answer">${escapeHtml(summary)}</div>
          ${ragWarnings(payload.warnings)}
        `;
      } else {
        const answer = payload.answer || (payload.configured ? "证据不足或暂无答案。" : "RAG 未配置或不可用。");
        const citations = (payload.citations || []).map(renderRagCitation).join("");
        panel.innerHTML = `
          <div class="rag-result-head">
            <strong>RAG回答</strong>
            <span>${escapeHtml(scope)}</span>
          </div>
          <div class="rag-question">${escapeHtml(result.question || "")}</div>
          <div class="rag-answer">${escapeHtml(answer).replace(/\n/g, "<br>")}</div>
          ${ragRetrievalSummary(payload.retrieval)}
          ${ragWarnings(payload.warnings)}
          ${citations ? `<div class="rag-citations">${citations}</div>` : ""}
        `;
      }
      panel.classList.add("show");
    }
    async function runRagIndex() {
      if (!state.allItems.length) {
        toast("当前筛选范围为空，无法索引");
        return;
      }
      const dayCount = dateRangeDayCount($("dateFrom").value, $("dateTo").value);
      if (!dayCount) {
        toast("日期范围不正确");
        return;
      }
      const scope = ragScopePayload();
      state.ragIndexInFlight = true;
      updateButtons();
      $("resultStatus").textContent = "RAG索引中...";
      $("chainStatus").textContent = `手动：/agent/rag/index · ${ragScopeLabel(scope)} · metadata-only`;
      try {
        const payload = await indexRagScope(scope);
        state.ragResult = { type: "index", payload };
        renderRagResult();
        toast(payload.configured ? `索引完成：${payload.indexed || 0} 更新，${payload.skipped || 0} 跳过` : "Embedding 未配置，无法索引");
      } catch (error) {
        toast(`RAG索引失败：${error.message}`);
      } finally {
        state.ragIndexInFlight = false;
        updateButtons();
      }
    }
    async function runRagAsk() {
      const question = $("ragQuestion").value.trim();
      if (!question) {
        toast("先输入要问缓存的问题");
        return;
      }
      if (!state.allItems.length) {
        toast("当前筛选范围为空，无法问答");
        return;
      }
      const dayCount = dateRangeDayCount($("dateFrom").value, $("dateTo").value);
      if (!dayCount) {
        toast("日期范围不正确");
        return;
      }
      const scope = ragScopePayload();
      const topK = boundedNumberInput("ragTopK", 8, 1, 20);
      state.ragAskInFlight = true;
      updateButtons();
      $("resultStatus").textContent = "RAG问答中...";
      $("chainStatus").textContent = `手动：/agent/ask · ${ragScopeLabel(scope)} · top_k ${topK} · metadata-only`;
      try {
        const payload = await askRagScope(scope, question, topK);
        state.ragResult = { type: "ask", payload, question };
        renderRagResult();
        const matches = payload.retrieval?.matches || 0;
        toast(payload.configured ? `RAG回答完成：${matches} 条证据` : "RAG/LLM 未配置，无法回答");
      } catch (error) {
        toast(`RAG问答失败：${error.message}`);
      } finally {
        state.ragAskInFlight = false;
        updateButtons();
      }
    }
    function clearRagResult() {
      $("ragQuestion").value = "";
      state.ragResult = null;
      renderRagResult();
      updateButtons();
      toast("已清除 RAG 回答");
    }
    function applyAiFilterGrouping(keys) {
      const mode = $("aiFilterMode").value === "importance" ? "importance" : "count";
      const threshold = boundedNumberInput("aiFilterThreshold", 70, 0, 100);
      const keepCount = boundedNumberInput("aiFilterKeepCount", 15, 1, AI_FILTER_MAX_SCAN);
      const decisions = keys
        .map((key) => [key, state.aiFilterResults.get(key)])
        .filter((entry) => entry[1])
        .sort((a, b) => Number(b[1].importance || 0) - Number(a[1].importance || 0));
      const recommended = new Set(mode === "count" ? decisions.slice(0, keepCount).map((entry) => entry[0]) : []);
      const maybeFloor = Math.max(0, threshold - 20);
      for (const [key, decision] of decisions) {
        const importance = Number(decision.importance || 0);
        const modelGroup = normalizedAiGroup(decision.group);
        if (mode === "count") {
          decision.display_group = recommended.has(key)
            ? "recommend"
            : (modelGroup === "reject" || importance < 40 ? "reject" : "maybe");
        } else {
          decision.display_group = importance >= threshold && modelGroup !== "reject"
            ? "recommend"
            : (modelGroup === "reject" || importance < maybeFloor ? "reject" : "maybe");
        }
      }
    }
    function clearAiFilterState({ clearQuery = false } = {}) {
      state.aiFilterActive = false;
      state.aiFilterQuery = "";
      state.aiFilterResults = new Map();
      if (clearQuery) $("aiFilterQuery").value = "";
    }
    async function recordAiFilterSignals(candidates) {
      if (!state.preferenceSettings.learning_enabled) return;
      let recorded = false;
      for (const paper of candidates || []) {
        const decision = state.aiFilterResults.get(paperReadingKey(paper));
        const group = normalizedAiGroup(decision?.display_group || decision?.group);
        if (!["recommend", "reject"].includes(group)) continue;
        const event = {
          source: "daily_ai_filter",
          query: state.aiFilterQuery,
          mode: $("aiFilterMode").value,
          display_group: group,
          ai_decision: aiDecisionEvent(decision, group),
          noise_tags: Array.isArray(decision?.noise_tags) ? decision.noise_tags.slice(0, 6) : [],
          quality_score: Number.isFinite(Number(decision?.quality_score)) ? Number(decision.quality_score) : 50,
          preference_score: Number.isFinite(Number(decision?.preference_score)) ? Number(decision.preference_score) : 50,
        };
        await applyLibraryActionClient(group === "recommend" ? "ai_recommend" : "ai_reject", [paper], event, { refreshPreference: false });
        recorded = true;
      }
      if (recorded) await loadPreferenceState();
    }
    async function runAiFilter() {
      const rawQuery = $("aiFilterQuery").value.trim();
      const queryLabel = rawQuery || DEFAULT_AI_FILTER_LABEL;
      const scanLimit = boundedNumberInput("aiFilterScanLimit", 60, 1, AI_FILTER_MAX_SCAN);
      const candidates = baseVisibleItems().slice(0, scanLimit);
      if (!candidates.length) {
        toast("当前加载结果为空，无法筛选");
        return;
      }
      state.aiFilterInFlight = true;
      clearAiFilterState();
      state.aiFilterQuery = queryLabel;
      updateButtons();
      $("resultStatus").textContent = `AI筛选中 0 / ${candidates.length}`;
      const profileMode = state.preferenceSettings.learning_enabled ? "自我学习开启" : "自我学习关闭";
      $("chainStatus").textContent = `手动：/agent/filter · ${queryLabel} · ${profileMode} · 当前加载结果 ${candidates.length} 条 · 单并发/${AI_FILTER_BATCH_DELAY_MS}ms 间隔`;
      const processedKeys = [];
      try {
        let processed = 0;
        for (const paper of candidates) {
          const payload = await filterPaperWithThrottle(paper, rawQuery, true);
          if (!payload.configured) {
            toast("LLM 未配置，无法 AI 筛选");
            clearAiFilterState();
            return;
          }
          const key = paperReadingKey(paper);
          state.aiFilterResults.set(key, payload);
          processedKeys.push(key);
          processed += 1;
          $("resultStatus").textContent = `AI筛选中 ${processed} / ${candidates.length}`;
          if (processed < candidates.length) await sleep(AI_FILTER_BATCH_DELAY_MS);
        }
        applyAiFilterGrouping(processedKeys);
        await recordAiFilterSignals(candidates);
        state.aiFilterActive = true;
        state.page = 1;
        renderVisibleItems();
        const counts = aiFilterCounts(displayItems());
        toast(`AI筛选完成：推荐 ${counts.recommend} / 待定 ${counts.maybe} / 不建议 ${counts.reject}`);
      } catch (error) {
        toast(`AI筛选失败：${error.message}`);
      } finally {
        state.aiFilterInFlight = false;
        updateButtons();
      }
    }
    function clearAiFilter() {
      clearAiFilterState({ clearQuery: true });
      state.page = 1;
      renderVisibleItems();
      toast("已清除 AI 筛选");
    }
    async function batchLibraryAction(action, label) {
      await runLibraryAction(action, targetBatchPapers(), label, { source: "daily_batch" });
    }
    async function translateBatch() {
      await translateResults(targetBatchPapers(), state.selectedKeys.size ? "选中结果" : "当前页");
    }
    async function translateCurrentPage() {
      await translateResults(state.currentItems || [], "当前页");
    }
    async function enrichBatch() {
      const items = targetBatchPapers();
      if (!items.length) {
        toast("当前没有可补全条目");
        return;
      }
      for (const paper of items) {
        await enrichPaper(paper);
      }
      toast(`批量补全完成：${items.length} 条`);
    }
    async function zoteroBatch() {
      await exportZoteroItems(targetBatchPapers());
    }
    async function translateResults(itemsOverride, label = "当前页") {
      const items = itemsOverride || state.currentItems || [];
      if (!items.length) {
        toast("没有可翻译的结果");
        return;
      }
      const pending = items.filter((paper) => !state.translations.has(paper.id));
      if (!pending.length) {
        toast(`${label}已翻译，无需重复请求`);
        return;
      }
      state.translationInFlight = true;
      updateButtons();
      const skipped = items.length - pending.length;
      $("resultStatus").textContent = `翻译中 0 / ${pending.length}${skipped ? `，跳过已翻译 ${skipped} 条` : ""}`;
      $("chainStatus").textContent = `手动：/agent/translate · brief · ${label} · 单并发/${TRANSLATE_BATCH_DELAY_MS}ms 间隔`;
      let translated = 0;
      const translatedPapers = [];
      try {
        for (const paper of pending) {
          const payload = await translatePaperWithThrottle(paper, "brief");
          if (!payload.configured) {
            toast("LLM 未配置，无法翻译");
            break;
          }
          if (payload.translation || payload.cn_flash_180 || payload.title_zh || payload.brief_skipped) state.translations.set(paper.id, payload);
          translatedPapers.push(paper);
          translated += 1;
          $("resultStatus").textContent = `翻译中 ${translated} / ${pending.length}${skipped ? `，跳过已翻译 ${skipped} 条` : ""}`;
          renderPapers(state.currentItems);
          if (translated < pending.length) await sleep(TRANSLATE_BATCH_DELAY_MS);
        }
        if (translatedPapers.length) await applyLibraryActionClient("translate", translatedPapers, { source: "daily_translate", style: "brief" });
        toast(`翻译完成：${translated} / ${pending.length}${skipped ? `，跳过 ${skipped} 条` : ""}`);
      } catch (error) {
        toast(`翻译失败：${error.message}`);
      } finally {
        state.translationInFlight = false;
        updateButtons();
      }
    }
    async function translateSinglePaper(paper) {
      if (!paper) return;
      if (state.detailTranslations.has(paper.id)) {
        toast("这条详情已经直译，不重复请求");
        return;
      }
      state.detailTranslationInFlightIds.add(paper.id);
      state.details.add(paper.id);
      updateButtons();
      renderPapers(state.currentItems);
      $("chainStatus").textContent = "手动：/agent/translate · detail · 当前详情";
      try {
        const payload = await translatePaperWithThrottle(paper, "detail");
        if (!payload.configured && !payload.detail_skipped) {
          toast("LLM 未配置，无法翻译");
          return;
        }
        if (payload.translation || payload.detail_translation || payload.detail_skipped) {
          state.detailTranslations.set(paper.id, payload);
          await applyLibraryActionClient("translate", [paper], { source: "daily_translate", style: "detail" });
          toast(payload.detail_skipped ? "没有可翻译详情" : "详情直译完成");
        } else {
          toast("详情暂无可显示翻译");
        }
      } catch (error) {
        toast(`详情直译失败：${error.message}`);
      } finally {
        state.detailTranslationInFlightIds.delete(paper.id);
        updateButtons();
        renderPapers(state.currentItems);
      }
    }
    function crawlWarningLabel(value) {
      const labels = {
        no_items_matched_date_range: "所选日期/来源没有匹配元数据",
      };
      return labels[value] || String(value || "");
    }
    function crawlIssueItems(run) {
      const issues = [];
      for (const result of run.source_results || []) {
        const source = result.source_key || result.endpoint_key || "source";
        if (result.error) issues.push(`${source}: ${result.error}`);
        for (const warning of result.warnings || []) {
          if (warning) issues.push(`${source}: ${crawlWarningLabel(warning)}`);
        }
      }
      for (const warning of run.warnings || []) {
        const label = crawlWarningLabel(warning);
        if (label && !issues.includes(label)) issues.push(label);
      }
      return issues;
    }
    function crawlIssueSummary(run) {
      const issue = crawlIssueItems(run)[0] || "";
      return issue.length > 120 ? `${issue.slice(0, 117)}...` : issue;
    }
    async function pollCrawl(runId) {
      for (let attempt = 0; attempt < 180; attempt += 1) {
        const run = await fetchJson(`/daily/crawl/${encodeURIComponent(runId)}`);
        const sourceDone = (run.source_results || []).length;
        const issueCount = crawlIssueItems(run).length;
        $("resultStatus").textContent = `抓取 ${run.status} · ${run.total_items || 0} 条`;
        $("chainStatus").textContent = `手动：/daily/crawl/${run.run_id} · ${sourceDone} / ${(run.source_keys || []).length} 源${issueCount ? ` · ${issueCount} 个来源警告` : ""}`;
        if (run.status === "completed") {
          const summary = crawlIssueSummary(run);
          if ((run.total_items || 0) === 0) {
            toast(`抓取完成但没有入库：${summary || "所选日期/来源没有匹配元数据"}`);
          } else if (summary) {
            toast(`抓取完成：${run.total_items || 0} 条；来源警告：${summary}`);
          } else {
            toast("抓取完成，已写入本地库");
          }
          state.page = 1;
          await loadPapers("刷新");
          return;
        }
        if (run.status === "failed") {
          toast(`抓取失败：${run.error || "unknown error"}`);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      toast("抓取仍在运行，稍后点刷新看缓存");
    }
    async function startCrawl() {
      if (!state.selectedDiscipline) {
        toast("先选学科，再抓取。不会全量请求 800+ 源。");
        openSourcePicker("discipline");
        return;
      }
      const dayCount = dateRangeDayCount($("dateFrom").value, $("dateTo").value);
      if (!dayCount) {
        toast("日期范围不正确");
        return;
      }
      const incompatible = incompatibleSelectedSources();
      if (incompatible.length) {
        const names = incompatible.slice(0, 3).join("、");
        const suffix = incompatible.length > 3 ? ` 等 ${incompatible.length} 个` : "";
        toast(`已选来源与学科不匹配或不可抓取：${names}${suffix}`);
        openSourcePicker("source");
        return;
      }
      const payload = {
        date_from: $("dateFrom").value,
        date_to: $("dateTo").value,
        discipline: state.selectedDiscipline,
        limit_per_source: 100,
      };
      const selected = Array.from(state.selectedSources);
      if (selected.length) payload.source = selected.join(",");
      $("resultStatus").textContent = "抓取排队中...";
      $("chainStatus").textContent = "手动：准备创建 /daily/crawl 入库任务";
      state.crawlInFlight = true;
      updateButtons();
      try {
        const run = await fetchJson("/daily/crawl", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (run.reused) {
          toast(run.reuse_reason === "cooldown" ? "刚抓过，直接复用缓存任务" : "已有抓取在跑，已复用");
        } else {
          toast(`已创建抓取任务：${run.source_keys.length} 源`);
        }
        await pollCrawl(run.run_id);
      } catch (error) {
        $("resultStatus").textContent = "抓取失败";
        $("chainStatus").textContent = "手动：/daily/crawl 创建失败";
        toast(`抓取失败：${error.message}`);
      } finally {
        state.crawlInFlight = false;
        updateButtons();
      }
    }
    async function startSchedule() {
      if (!state.selectedDiscipline) {
        toast("先选学科，再设置定时获取。");
        openSourcePicker("discipline");
        return;
      }
      const intervalText = window.prompt("每隔多少分钟自动抓取当前学科/来源？最少 15。", "180");
      if (intervalText === null) return;
      const interval = Math.max(15, Number.parseInt(intervalText, 10) || 180);
      const dayCount = dateRangeDayCount($("dateFrom").value, $("dateTo").value);
      const payload = {
        discipline: state.selectedDiscipline,
        interval_minutes: interval,
        lookback_days: Math.max(0, Math.min(30, dayCount ? dayCount - 1 : 0)),
        limit_per_source: 100,
      };
      const selected = Array.from(state.selectedSources);
      if (selected.length) payload.source = selected.join(",");
      $("chainStatus").textContent = "定时：准备写入 /daily/schedules";
      try {
        const schedule = await fetchJson("/daily/schedules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        $("chainStatus").textContent = `定时：/daily/schedules · 下次 ${schedule.next_run_at}`;
        toast(`已设置定时获取：每 ${schedule.interval_minutes} 分钟`);
      } catch (error) {
        $("chainStatus").textContent = "定时：/daily/schedules 创建失败";
        toast(`定时失败：${error.message}`);
      }
    }

    function buildDailyExportUrl(format) {
      const params = new URLSearchParams();
      params.set("date_from", $("dateFrom").value);
      params.set("date_to", $("dateTo").value);
      params.set("format", format);
      params.set("limit_per_source", "500");
      const q = $("search").value.trim();
      if (q) params.set("q", q);
      if (state.selectedDiscipline) params.set("discipline", state.selectedDiscipline);
      if (state.selectedSources.size) params.set("source", Array.from(state.selectedSources).join(","));
      return `/daily/export?${params.toString()}`;
    }

    function exportCurrentResults(format) {
      $("exportMenu").classList.remove("open");
      if (!state.allItems.length) {
        toast("当前没有可导出的缓存结果");
        return;
      }
      const link = document.createElement("a");
      link.href = buildDailyExportUrl(format);
      link.rel = "noreferrer";
      document.body.appendChild(link);
      link.click();
      link.remove();
      $("chainStatus").textContent = `手动：/daily/export · ${format} · 当前筛选范围`;
      toast(`开始导出 ${state.allItems.length} 条`);
    }

    async function exportZoteroItems(papers) {
      const items = (papers || []).filter(Boolean);
      if (!items.length) {
        toast("当前没有可发送条目");
        return;
      }
      let status = { configured: false };
      try {
        status = await fetchJson("/zotero/status");
      } catch (error) {
        const message = `检查 Zotero 状态失败：${error.message || "unknown error"}。是否改为导出 RIS 文件？`;
        if (!window.confirm(message)) {
          toast("已取消 RIS 导出");
          return;
        }
      }
      if (status.configured) {
        try {
          await fetchJson("/zotero/items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ items }),
          });
          await applyLibraryActionClient("zotero", items, { source: "daily" });
          toast(`已发送到 Zotero：${items.length} 条`);
          return;
        } catch (error) {
          const message = `发送到 Zotero 失败：${error.message || "unknown error"}。是否改为导出 RIS 文件？`;
          if (!window.confirm(message)) {
            toast("已取消 RIS 导出");
            return;
          }
        }
      }
      const response = await fetch("/zotero/export?format=ris", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "paperlite-zotero.ris";
      a.click();
      URL.revokeObjectURL(url);
      await applyLibraryActionClient("export", items, { source: "daily_zotero_fallback", format: "ris" });
      toast(`已导出 RIS：${items.length} 条`);
    }
    async function exportZotero(paper) {
      if (!paper) return;
      await exportZoteroItems([paper]);
    }
    async function enrichPaper(paper) {
      if (!paper) return;
      state.enrichments.set(paper.id, {
        status: "loading",
        label: "补全中",
        message: "正在查 OpenAlex / Crossref / PubMed / Europe PMC...",
        warnings: [],
      });
      renderPapers(state.currentItems);
      $("chainStatus").textContent = "手动：/daily/enrich · OpenAlex/Crossref/PubMed/Europe PMC";
      try {
        const enriched = await fetchJson(`/daily/enrich?source=${encodeURIComponent(ENRICHERS)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(paper),
        });
        const merged = mergeClientPaper(paper, enriched);
        const changes = enrichmentChanges(paper, merged);
        const warnings = (merged.raw && Array.isArray(merged.raw.enrich_warnings)) ? merged.raw.enrich_warnings : [];
        replacePaperEverywhere(paper.id, merged);
        state.enrichments.set(paper.id, {
          status: warnings.length ? "warning" : "done",
          label: "补全完成",
          message: changes.length ? `新增/更新：${changes.join("、")}` : "已查询，暂无新增字段。",
          warnings,
          evidence: enrichmentEvidence(merged),
        });
        state.details.add(paper.id);
        await applyLibraryActionClient("enrich", [merged], { source: "daily_card" });
        renderPapers(state.currentItems);
        toast(changes.length ? `补全完成：${changes.join("、")}` : "补全完成：暂无新增字段");
      } catch (error) {
        state.enrichments.set(paper.id, {
          status: "error",
          label: "补全失败",
          message: error.message,
          warnings: [],
        });
        renderPapers(state.currentItems);
        toast(`补全失败：${error.message}`);
      }
    }
