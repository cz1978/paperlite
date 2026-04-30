    function aiGroupLabel(group) {
      return {
        recommend: "推荐组",
        maybe: "待定组",
        reject: "不建议组",
      }[group] || "待定组";
    }
    function aiGroupOrder(group) {
      return { recommend: 0, maybe: 1, reject: 2 }[group] ?? 1;
    }
    function normalizedAiGroup(value) {
      return ["recommend", "maybe", "reject"].includes(value) ? value : "maybe";
    }
    function aiDecisionGroup(decision) {
      return normalizedAiGroup(decision?.display_group || decision?.group);
    }
    function aiDecisionForPaper(paper) {
      return state.aiFilterResults.get(paperReadingKey(paper));
    }
    function aiDecisionEvent(decision, displayGroup) {
      if (!decision) return null;
      return {
        display_group: displayGroup || aiDecisionGroup(decision),
        group: normalizedAiGroup(decision.group),
        importance: Number.isFinite(Number(decision.importance)) ? Number(decision.importance) : 50,
        quality_score: Number.isFinite(Number(decision.quality_score)) ? Number(decision.quality_score) : 50,
        preference_score: Number.isFinite(Number(decision.preference_score)) ? Number(decision.preference_score) : 50,
        noise_tags: Array.isArray(decision.noise_tags) ? decision.noise_tags.slice(0, 6) : [],
        matched_preferences: Array.isArray(decision.matched_preferences) ? decision.matched_preferences.slice(0, 5) : [],
        quality_reasons: Array.isArray(decision.quality_reasons) ? decision.quality_reasons.slice(0, 5) : [],
        reason: decision.reason || "",
        confidence: Number.isFinite(Number(decision.confidence)) ? Number(decision.confidence) : null,
        profile_used: Boolean(decision.profile_used),
      };
    }
    function eventWithAiDecision(paper, event = {}) {
      const decision = aiDecisionForPaper(paper);
      const aiDecision = aiDecisionEvent(decision);
      if (!aiDecision) return event;
      return {
        ...event,
        ai_filter_query: state.aiFilterQuery,
        ai_decision: aiDecision,
        noise_tags: aiDecision.noise_tags,
        quality_score: aiDecision.quality_score,
        preference_score: aiDecision.preference_score,
      };
    }
    function aiFilterCounts(items) {
      const counts = { recommend: 0, maybe: 0, reject: 0 };
      for (const paper of items || []) {
        const decision = aiDecisionForPaper(paper);
        if (!decision) continue;
        counts[aiDecisionGroup(decision)] += 1;
      }
      return counts;
    }
    function renderAiFilterDecision(decision) {
      if (!decision) return "";
      const group = aiDecisionGroup(decision);
      const importance = Number.isFinite(Number(decision.importance)) ? Number(decision.importance) : 50;
      const quality = Number.isFinite(Number(decision.quality_score)) ? Number(decision.quality_score) : 50;
      const preference = Number.isFinite(Number(decision.preference_score)) ? Number(decision.preference_score) : 50;
      const confidence = Number.isFinite(Number(decision.confidence)) ? ` · 把握 ${Math.round(Number(decision.confidence) * 100)}%` : "";
      const noiseTags = Array.isArray(decision.noise_tags) && decision.noise_tags.length
        ? ` · 噪音 ${decision.noise_tags.map((tag) => escapeHtml(tag)).join(", ")}`
        : "";
      return `
        <div class="ai-filter-decision">
          <span class="ai-filter-label">${escapeHtml(aiGroupLabel(group))}</span>
          重要度 ${importance}/100 · 质量 ${quality}/100 · 偏好 ${preference}/100${confidence}${noiseTags} · ${escapeHtml(decision.reason || "AI 未给出原因")}
        </div>
      `;
    }
    function groupAiFilteredItems(items) {
      const buckets = { recommend: [], maybe: [], reject: [] };
      for (const paper of items || []) {
        buckets[aiDecisionGroup(aiDecisionForPaper(paper))].push(paper);
      }
      return buckets;
    }

    function renderPapers(items) {
      if (!items.length) {
        const message = state.viewMode === "favorites"
          ? "收藏夹还是空的。回到每日流，点论文卡片上的“收藏”就会出现在这里。"
          : state.aiFilterActive && state.allItems.length
          ? "AI 筛选后没有可显示条目。可以点“清除AI筛选”恢复。"
          : state.hideRead && state.allItems.length
          ? "当前结果都已读并被隐藏。可以点“显示已读”恢复。"
          : "当前库没有内容。先选学科并点抓取，或换时间段、来源后刷新。";
        $("paperList").innerHTML = `<div class="empty">${message}</div>`;
        return;
      }
      const renderPaperCard = (paper) => {
        const cats = (paper.categories || paper.concepts || []).slice(0, 2).join(" / ");
        const identifier = paperIdentifierLabel(paper);
        const isOpen = state.details.has(paper.id);
        const translation = state.translations.get(paper.id);
        const detailTranslation = state.detailTranslations.get(paper.id);
        const enrichment = state.enrichments.get(paper.id);
        const enrichBusy = enrichment?.status === "loading";
        const readKey = paperReadingKey(paper);
        const isRead = state.readKeys.has(readKey);
        const isFavorite = state.favoriteKeys.has(readKey);
        const isSelected = state.selectedKeys.has(readKey);
        const aiDecision = aiDecisionForPaper(paper);
        const aiClass = aiDecision ? `ai-${aiDecisionGroup(aiDecision)}` : "";
        const dailySources = Array.isArray(paper._daily_sources) ? paper._daily_sources : [];
        const sourceEvidence = dailySources.length > 1
          ? `<span class="source-evidence" title="${escapeHtml(dailySources.join(" / "))}">多来源 ${dailySources.length}</span>`
          : "";
        return `
          <article class="paper ${isRead ? "is-read" : ""} ${isFavorite ? "is-favorite" : ""} ${aiClass}" data-paper-id="${escapeHtml(paper.id)}">
            <input class="paper-select" data-action="select" type="checkbox" aria-label="选择论文" ${isSelected ? "checked" : ""}>
            <div class="paper-time">${escapeHtml(fmtDay(paper.published_at) || "--")}</div>
            <div>
              <h2 class="paper-title">${escapeHtml(paper.title || "Untitled")}</h2>
              <div class="paper-meta">
                <span class="paper-source">${escapeHtml(paper.source || "")}</span>
                <span>${escapeHtml(cats || paper.venue || paper.journal || "")}</span>
                <span>${escapeHtml(identifier)}</span>
                ${sourceEvidence}
              </div>
            </div>
            <div class="paper-actions">
              <button class="btn tiny ${isRead ? "dark" : ""}" data-action="read" type="button">${isRead ? "已读" : "未读"}</button>
              <button class="btn tiny ${isFavorite ? "dark" : ""}" data-action="favorite" type="button">${isFavorite ? "已收藏" : "收藏"}</button>
              <button class="btn tiny" data-action="detail" type="button">详情</button>
              <button class="btn tiny" data-action="zotero" title="单条发送到 Zotero；未配置时导出 RIS；发送失败时询问是否导出 RIS" type="button">Zotero</button>
              <button class="btn tiny" data-action="enrich" title="单条元数据补全：OpenAlex / Crossref / PubMed / Europe PMC" type="button" ${enrichBusy ? "disabled" : ""}>${enrichBusy ? "补全中" : "补全"}</button>
            </div>
            ${isOpen ? renderDetail(paper) : ""}
            ${enrichment ? renderEnrichmentStatus(enrichment) : ""}
            ${detailTranslation ? renderDetailTranslation(detailTranslation) : ""}
            ${translation ? renderTranslation(translation) : ""}
            ${aiDecision ? renderAiFilterDecision(aiDecision) : ""}
          </article>
        `;
      };
      if (state.aiFilterActive) {
        const groups = groupAiFilteredItems(items);
        $("paperList").innerHTML = ["recommend", "maybe", "reject"].map((group) => `
          <section class="ai-group" data-ai-group="${group}">
            <div class="ai-group-head"><span>${aiGroupLabel(group)}</span><span>${groups[group].length} 条</span></div>
            ${groups[group].map(renderPaperCard).join("") || `<div class="empty">${aiGroupLabel(group)}暂无条目</div>`}
          </section>
        `).join("");
      } else {
        $("paperList").innerHTML = items.map(renderPaperCard).join("");
      }
      for (const card of $("paperList").querySelectorAll(".paper")) {
        const id = card.dataset.paperId;
        const paper = state.currentItems.find((item) => item.id === id);
        card.querySelector('[data-action="detail"]').addEventListener("click", () => {
          let shouldLoadRelated = false;
          if (state.details.has(id)) state.details.delete(id);
          else {
            state.details.add(id);
            shouldLoadRelated = true;
            applyLibraryActionClient("detail", [paper], { source: "daily_card" });
          }
          renderPapers(state.currentItems);
          if (shouldLoadRelated) loadRelatedPapers(paper);
        });
        card.querySelector('[data-action="select"]').addEventListener("change", (event) => {
          const key = paperReadingKey(paper);
          if (event.target.checked) state.selectedKeys.add(key);
          else state.selectedKeys.delete(key);
          updateButtons();
        });
        card.querySelector('[data-action="read"]').addEventListener("click", () => toggleRead(paper));
        card.querySelector('[data-action="favorite"]').addEventListener("click", () => toggleFavorite(paper));
        card.querySelector('[data-action="zotero"]').addEventListener("click", () => exportZotero(paper));
        card.querySelector('[data-action="enrich"]').addEventListener("click", () => enrichPaper(paper));
        const translateDetail = card.querySelector('[data-action="translate-detail"]');
        if (translateDetail) translateDetail.addEventListener("click", () => translateSinglePaper(paper));
      }
    }
