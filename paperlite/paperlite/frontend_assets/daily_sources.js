    function sourceKindOf(source) {
      const kind = source.source_kind_key || source.catalog_kind || source.group || source.source_type || "other";
      if (kind === "preprint" || kind === "journal" || kind === "metadata" || kind === "working_papers" || kind === "news" || kind === "local") return kind;
      return "other";
    }
    function sourceStatusLabel(value) {
      const labels = {
        active: "可用",
        ok: "可用",
        temporarily_unavailable: "暂不可用",
        blocked_403: "403 阻断",
        timeout: "超时",
        missing_endpoint: "无可用端点",
        missing_catalog_record: "缺目录记录",
        candidate: "候选",
        needs_review: "待复核",
        duplicate: "重复源",
        connector_only: "仅连接器",
      };
      return labels[value] || value;
    }
    function sourceAvailability(source) {
      const badges = [];
      let available = true;
      if (!source.supports_latest) {
        available = false;
        badges.push({ label: "不可抓取", tone: "bad" });
      }
      const health = source.health_status || "";
      if (health && health !== "active" && health !== "ok") {
        available = false;
        badges.push({ label: sourceStatusLabel(health), tone: health === "candidate" ? "warn" : "bad" });
      }
      const quality = source.quality_status || "";
      if (quality === "temporarily_unavailable" && health !== "temporarily_unavailable") {
        available = false;
        badges.push({ label: "暂不可用", tone: "bad" });
      } else if (quality === "candidate" || quality === "needs_review" || source.needs_review) {
        badges.push({ label: sourceStatusLabel(quality || "needs_review"), tone: "warn" });
      } else if (quality === "duplicate" || quality === "connector_only") {
        badges.push({ label: sourceStatusLabel(quality), tone: "warn" });
      }
      return { available, badges };
    }
    function renderSourceBadges(source) {
      const seen = new Set();
      return sourceAvailability(source).badges
        .filter((badge) => {
          if (seen.has(badge.label)) return false;
          seen.add(badge.label);
          return true;
        })
        .map((badge) => `<span class="source-status-badge ${badge.tone || ""}">${escapeHtml(badge.label)}</span>`)
        .join("");
    }
    function sourceMatchesDiscipline(source, discipline = state.selectedDiscipline) {
      if (!discipline) return true;
      if (source.primary_discipline_key === discipline || (source.discipline_keys || []).includes(discipline)) return true;
      return discipline !== "multidisciplinary" && Boolean(source.multidisciplinary_supplement);
    }
    function sourceCrawlCompatible(source, discipline = state.selectedDiscipline) {
      return sourceMatchesDiscipline(source, discipline) && sourceAvailability(source).available;
    }
    function incompatibleSelectedSources(discipline = state.selectedDiscipline) {
      return Array.from(state.selectedSources)
        .map((key) => state.sources.find((source) => source.name === key))
        .filter((source) => !source || !sourceCrawlCompatible(source, discipline))
        .map((source) => source?.display_name || source?.name || "unknown source");
    }
    function pruneSelectedSourcesForDiscipline() {
      if (!state.selectedSources.size || !state.selectedDiscipline) return 0;
      let removed = 0;
      for (const key of Array.from(state.selectedSources)) {
        const source = state.sources.find((item) => item.name === key);
        if (!source || !sourceCrawlCompatible(source)) {
          state.selectedSources.delete(key);
          removed += 1;
        }
      }
      return removed;
    }
    function runnableLatestSourcesForDiscipline() {
      return state.sources.filter((source) => source.supports_latest && sourceMatchesDiscipline(source));
    }
    function effectiveSourceKeys() {
      const selected = Array.from(state.selectedSources);
      if (selected.length) return selected;
      if (state.selectedDiscipline) return runnableLatestSourcesForDiscipline().map((source) => source.name);
      return [];
    }
    function effectiveSourceDescription(keys) {
      if (state.selectedSources.size) return `已选 ${keys.length} 个来源`;
      if (state.selectedDiscipline) {
        const supplementCount = runnableLatestSourcesForDiscipline().filter((source) => source.multidisciplinary_supplement).length;
        return `${selectedDisciplineLabel().replace("学科：", "")}${keys.length ? ` / 已选 ${keys.length} 源` : ""}${supplementCount ? ` / 含综合补充 ${supplementCount}` : ""}`;
      }
      return "全部缓存";
    }
    function disciplineOptions() {
      const seen = new Map();
      for (const source of state.sources) {
        const key = source.primary_discipline_key || "unclassified";
        if (!seen.has(key)) seen.set(key, source.primary_discipline_label || source.primary_discipline || key);
      }
      const q = state.sourceQuery.trim().toLowerCase();
      return Array.from(seen.entries())
        .filter(([key, label]) => {
          if (!q) return true;
          const hay = [key, label, ...(disciplineAliases[key] || [])].join(" ").toLowerCase();
          return hay.includes(q);
        })
        .sort((a, b) => a[1].localeCompare(b[1], "zh-CN"));
    }
    function sourceMatches(source) {
      if (state.selectedOnly && !state.selectedSources.has(source.name)) return false;
      if (state.sourceKind !== "all" && sourceKindOf(source) !== state.sourceKind) return false;
      if (!sourceMatchesDiscipline(source)) return false;
      const q = state.sourceQuery.trim().toLowerCase();
      if (!q) return true;
      const hay = [
        source.name, source.display_name, source.publisher, source.category_label,
        source.primary_discipline_label, source.source_kind_label, source.url,
        source.health_status, source.quality_status, sourceStatusLabel(source.health_status || ""),
        sourceStatusLabel(source.quality_status || "")
      ].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    }
    function selectedSourceLabel() {
      if (!state.selectedSources.size) return "来源：全部";
      if (state.selectedSources.size === 1) {
        const key = Array.from(state.selectedSources)[0];
        const source = state.sources.find((item) => item.name === key);
        return `来源：${source?.display_name || key}`;
      }
      return `来源：已选 ${state.selectedSources.size}`;
    }
    function selectedDisciplineLabel() {
      if (!state.selectedDiscipline) return "学科：全部";
      const source = state.sources.find((item) => item.primary_discipline_key === state.selectedDiscipline || (item.discipline_keys || []).includes(state.selectedDiscipline));
      return `学科：${source?.primary_discipline_label || state.selectedDiscipline}`;
    }
    function updateButtons() {
      $("sourceBtn").firstElementChild.textContent = selectedSourceLabel();
      $("disciplineBtn").firstElementChild.textContent = selectedDisciplineLabel();
      const sourceScope = state.selectedSources.size ? `已选 ${state.selectedSources.size} 源` : "全部来源";
      const disciplineScope = state.selectedDiscipline ? selectedDisciplineLabel().replace("学科：", "") : "全部学科";
      $("headingTitle").textContent = state.viewMode === "favorites" ? "收藏夹" : "今天内容";
      $("scopeText").textContent = state.viewMode === "favorites" ? "SQLite 个人库 / 收藏" : `${sourceScope} / ${disciplineScope}`;
      $("pageText").textContent = `第 ${state.page} 页`;
      $("prevBtn").disabled = state.page <= 1;
      $("nextBtn").disabled = !state.hasMore;
      $("dailyViewBtn").classList.toggle("dark", state.viewMode === "daily");
      $("favoritesViewBtn").classList.toggle("dark", state.viewMode === "favorites");
      $("dailyViewBtn").disabled = state.libraryViewInFlight || state.crawlInFlight;
      $("favoritesViewBtn").disabled = state.libraryViewInFlight || state.crawlInFlight;
      $("hideReadBtn").classList.toggle("dark", state.hideRead);
      $("hideReadBtn").textContent = state.hideRead ? "显示已读" : "隐藏已读";
      $("crawlBtn").disabled = state.crawlInFlight;
      $("scheduleBtn").disabled = state.crawlInFlight;
      $("translateBtn").disabled = state.translationInFlight || state.aiFilterInFlight || state.detailTranslationInFlightIds.size > 0 || state.libraryViewInFlight || !state.allItems.length;
      $("exportBtn").disabled = state.viewMode !== "daily" || !state.allItems.length;
      const targetCount = state.selectedKeys.size || state.currentItems.length;
      $("selectionText").textContent = state.selectedKeys.size
        ? `已选 ${state.selectedKeys.size} 条；批量动作处理选中项。${state.libraryAvailable ? "" : " Library API 不可用，使用本地状态。"}`
        : `未选中；批量动作默认处理当前页 ${state.currentItems.length} 条。${state.libraryAvailable ? "" : " Library API 不可用，使用本地状态。"}`;
      $("aiFilterBtn").disabled = !state.allItems.length || state.aiFilterInFlight || state.translationInFlight || state.crawlInFlight || state.libraryViewInFlight;
      $("clearAiFilterBtn").disabled = state.aiFilterInFlight || (!state.aiFilterActive && !state.aiFilterResults.size && !$("aiFilterQuery").value.trim());
      $("ragIndexBtn").disabled = !state.allItems.length || state.ragIndexInFlight || state.ragAskInFlight || state.crawlInFlight || state.libraryViewInFlight;
      $("ragAskBtn").disabled = !state.allItems.length || state.ragIndexInFlight || state.ragAskInFlight || state.crawlInFlight || state.libraryViewInFlight || !$("ragQuestion").value.trim();
      $("clearRagBtn").disabled = state.ragIndexInFlight || state.ragAskInFlight || (!state.ragResult && !$("ragQuestion").value.trim());
      $("clearLearningDataBtn").disabled = state.preferenceInFlight;
      $("learningEnabled").checked = Boolean(state.preferenceSettings.learning_enabled);
      for (const id of ["batchReadBtn", "batchFavoriteBtn", "batchHideBtn", "batchTranslateBtn", "batchEnrichBtn", "batchZoteroBtn"]) {
        $(id).disabled = !targetCount || state.translationInFlight || state.aiFilterInFlight || state.crawlInFlight || state.libraryViewInFlight;
      }
    }

    function renderSourceTabs() {
      const counts = new Map([["all", state.sources.length]]);
      for (const source of state.sources) {
        const kind = sourceKindOf(source);
        counts.set(kind, (counts.get(kind) || 0) + 1);
      }
      const keys = ["all", "preprint", "journal", "metadata", "working_papers", "news", "local", "other"].filter((key) => counts.has(key));
      $("sourceTabs").innerHTML = keys.map((key) => `
        <button class="tab ${state.sourceKind === key ? "active" : ""}" data-kind="${escapeHtml(key)}" type="button">
          ${escapeHtml(sourceKindLabels[key] || key)} ${counts.get(key) || 0}
        </button>
      `).join("");
      for (const button of $("sourceTabs").querySelectorAll("button")) {
        button.addEventListener("click", () => {
          state.sourceKind = button.dataset.kind;
          state.sourceRenderCount = 120;
          renderSourcePicker();
        });
      }
    }

    function renderSourcePicker() {
      renderSourceTabs();
      const filtered = state.sources.filter(sourceMatches);
      const grouped = new Map();
      for (const source of filtered.slice(0, state.sourceRenderCount)) {
        const group = source.category_label || `${source.primary_discipline_label || "其他"} / ${source.source_kind_label || sourceKindLabels[sourceKindOf(source)] || "其他"}`;
        if (!grouped.has(group)) grouped.set(group, []);
        grouped.get(group).push(source);
      }
      const parts = [];
      for (const [group, items] of grouped) {
        const unavailableInGroup = items.filter((source) => !sourceAvailability(source).available).length;
        parts.push(`<div class="source-group-head"><span>${escapeHtml(group)}</span><span>${items.length} 源${unavailableInGroup ? ` / ${unavailableInGroup} 不可用` : ""}</span></div>`);
        for (const source of items) {
          const checked = state.selectedSources.has(source.name);
          const availability = sourceAvailability(source);
          const badges = renderSourceBadges(source);
          parts.push(`
            <label class="source-row ${checked ? "selected" : ""} ${availability.available ? "" : "unavailable"}">
              <input type="checkbox" value="${escapeHtml(source.name)}" ${checked ? "checked" : ""}>
              <span>
                ${escapeHtml(source.display_name || source.name)} · ${escapeHtml(source.publisher || source.source_kind_label || source.group || "")}
                <div class="source-sub">
                  ${escapeHtml(source.name)}${source.supports_search ? " · 可搜索" : ""}${badges ? `<span class="source-badges">${badges}</span>` : ""}
                </div>
              </span>
              <span class="source-count">${state.sourceCounts.get(source.name) || 0}</span>
            </label>
          `);
        }
      }
      if (filtered.length > state.sourceRenderCount) {
        parts.push(`<button class="show-more" id="showMoreSources" type="button">显示更多（${state.sourceRenderCount} / ${filtered.length}）</button>`);
      }
      $("sourceList").innerHTML = parts.join("") || `<div class="empty">没有匹配来源</div>`;
      const unavailableCount = filtered.filter((source) => !sourceAvailability(source).available).length;
      const unavailableText = unavailableCount ? `，${unavailableCount} 个不可用/不可抓取` : "";
      $("sourceFootText").textContent = state.selectedSources.size ? `已选 ${state.selectedSources.size} 个来源${unavailableText}` : `全部来源 / 当前 ${filtered.length} 个${unavailableText}`;
      for (const input of $("sourceList").querySelectorAll("input[type=checkbox]")) {
        input.addEventListener("change", () => {
          if (input.checked) state.selectedSources.add(input.value);
          else state.selectedSources.delete(input.value);
          updateButtons();
          renderSourcePicker();
        });
      }
      const more = $("showMoreSources");
      if (more) {
        more.addEventListener("click", () => {
          state.sourceRenderCount += 160;
          renderSourcePicker();
        });
      }
    }

    function renderDisciplinePicker() {
        const options = disciplineOptions();
        $("sourceTabs").innerHTML = "";
        $("sourceList").innerHTML = `
          <label class="source-row ${!state.selectedDiscipline ? "selected" : ""}">
            <input type="radio" name="discipline" value="" ${!state.selectedDiscipline ? "checked" : ""}>
            <span>全部学科<div class="source-sub">不限制学科</div></span><span class="source-count">${state.sources.length}</span>
          </label>
          ${options.map(([key, label]) => {
            const count = state.sources.filter((source) => (
              source.primary_discipline_key === key
              || (source.discipline_keys || []).includes(key)
              || (key !== "multidisciplinary" && source.multidisciplinary_supplement)
            )).length;
            return `
              <label class="source-row ${state.selectedDiscipline === key ? "selected" : ""}">
                <input type="radio" name="discipline" value="${escapeHtml(key)}" ${state.selectedDiscipline === key ? "checked" : ""}>
                <span>${escapeHtml(label)}<div class="source-sub">${escapeHtml(key)}${key !== "multidisciplinary" ? " · 含综合补充" : ""}</div></span><span class="source-count">${count}</span>
              </label>
            `;
          }).join("")}
        `;
        $("sourceFootText").textContent = "选择学科后会限制来源列表和实际请求来源";
        for (const input of $("sourceList").querySelectorAll("input[type=radio]")) {
          input.addEventListener("change", () => {
            state.selectedDiscipline = input.value;
            state.sourceRenderCount = 120;
            const removed = pruneSelectedSourcesForDiscipline();
            if (removed) toast(`已清除 ${removed} 个与该学科不匹配的来源`);
            updateButtons();
            $("sourcePopover").classList.remove("open");
            state.page = 1;
            loadPapers();
          });
        }
    }

    function openSourcePicker(mode) {
      const nextMode = mode === "discipline" ? "discipline" : "source";
      if (state.pickerMode !== nextMode) {
        state.sourceQuery = "";
        $("sourceSearch").value = "";
      }
      state.pickerMode = nextMode;
      if (state.pickerMode === "discipline") {
        renderDisciplinePicker();
      } else {
        renderSourcePicker();
      }
      $("sourcePopover").classList.add("open");
    }
