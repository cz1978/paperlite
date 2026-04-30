    function cacheParams(dateFrom, dateTo, limitPerSource) {
      const params = new URLSearchParams();
      const selected = Array.from(state.selectedSources);
      if (selected.length) params.set("source", selected.join(","));
      if (state.selectedDiscipline) params.set("discipline", state.selectedDiscipline);
      params.set("date_from", dateFrom);
      params.set("date_to", dateTo);
      params.set("limit_per_source", String(limitPerSource));
      params.set("format", "json");
      return params;
    }
    function paperMatchesQuery(paper, query) {
      if (!query) return true;
      const hay = [
        paper.title,
        paper.abstract,
        paper.source,
        paper._daily_source_display,
        ...(paper._daily_sources || []),
        paper.venue,
        paper.journal,
        paper.publisher,
        paper.doi,
        ...(paper.categories || []),
        ...(paper.concepts || []),
      ].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(query.toLowerCase());
    }
    function paperCanonicalKey(paper) {
      return paper._canonical_key || paper.doi || paper.pmid || paper.pmcid || paper.openalex_id || paper.id;
    }
    function paperReadingKey(paper) {
      return String(paper._library_key || paperCanonicalKey(paper) || paper.id || "").trim();
    }
    function toggleSetValue(set, value) {
      if (!value) return false;
      if (set.has(value)) {
        set.delete(value);
        return false;
      }
      set.add(value);
      return true;
    }
    function mirrorReadingState() {
      saveStoredSet(READ_STORAGE_KEY, state.readKeys);
      saveStoredSet(FAVORITE_STORAGE_KEY, state.favoriteKeys);
      saveStoredSet(HIDDEN_STORAGE_KEY, state.hiddenKeys);
    }
    function attachLibraryKey(libraryItem) {
      if (!libraryItem?.library_key) return;
      for (const item of [...state.allItems, ...state.currentItems]) {
        if (item.id === libraryItem.paper_id || paperCanonicalKey(item) === libraryItem.library_key) {
          item._library_key = libraryItem.library_key;
        }
      }
    }
    function applyLibraryStateItem(libraryItem) {
      if (!libraryItem?.library_key) return;
      attachLibraryKey(libraryItem);
      const key = libraryItem.library_key;
      if (libraryItem.read) state.readKeys.add(key); else state.readKeys.delete(key);
      if (libraryItem.favorite) state.favoriteKeys.add(key); else state.favoriteKeys.delete(key);
      if (libraryItem.hidden) state.hiddenKeys.add(key); else state.hiddenKeys.delete(key);
    }
    async function syncLibraryState(items) {
      if (!items.length) return;
      try {
        const payload = await fetchJson("/library/state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items }),
        });
        for (const item of payload.items || []) applyLibraryStateItem(item);
        state.libraryAvailable = true;
        mirrorReadingState();
      } catch (_) {
        state.libraryAvailable = false;
      }
    }
    function libraryItemsToPapers(items) {
      const papers = [];
      for (const item of items || []) {
        if (!item?.paper || typeof item.paper !== "object") continue;
        const paper = { ...item.paper, _library_key: item.library_key };
        papers.push(paper);
        applyLibraryStateItem({ ...item, paper });
      }
      mirrorReadingState();
      return papers;
    }
    async function loadFavoriteShelf() {
      state.libraryViewInFlight = true;
      state.viewMode = "favorites";
      state.page = 1;
      clearAiFilterState();
      clearRelatedState();
      updateButtons();
      $("resultStatus").textContent = "收藏夹加载中...";
      $("chainStatus").textContent = "手动：/library/items?state=favorite · SQLite 收藏夹";
      try {
        const payload = await fetchJson("/library/items?state=favorite&limit=500");
        state.allItems = libraryItemsToPapers(payload.items || []);
        state.currentItems = [];
        state.sourceCounts = new Map();
        state.lastActiveSources = 0;
        state.hasMore = false;
        state.libraryAvailable = true;
        $("chainStatus").textContent = `手动：/library/items · 收藏 ${state.allItems.length} 条`;
        renderVisibleItems(0);
      } catch (error) {
        state.allItems = [];
        state.currentItems = [];
        clearRelatedState();
        state.hasMore = false;
        state.libraryAvailable = false;
        $("resultStatus").textContent = "收藏夹加载失败";
        $("chainStatus").textContent = "读取链路：/library/items 失败";
        $("paperList").innerHTML = `<div class="empty">收藏夹加载失败：${escapeHtml(error.message)}</div>`;
        updateButtons();
      } finally {
        state.libraryViewInFlight = false;
        updateButtons();
      }
    }
    async function applyLibraryActionClient(action, papers, event, options = {}) {
      const items = (papers || []).filter(Boolean);
      if (!items.length) return false;
      const refreshPreference = options.refreshPreference !== false;
      try {
        const payload = await fetchJson("/library/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, items, event: event || {} }),
        });
        for (const item of payload.updated || []) applyLibraryStateItem(item);
        state.libraryAvailable = true;
        mirrorReadingState();
        if (refreshPreference) await loadPreferenceState();
        return true;
      } catch (_) {
        state.libraryAvailable = false;
        return false;
      }
    }
    function applyLocalLibraryAction(action, papers) {
      for (const paper of papers || []) {
        const key = paperReadingKey(paper);
        if (!key) continue;
        if (action === "read") state.readKeys.add(key);
        if (action === "unread") state.readKeys.delete(key);
        if (action === "favorite") state.favoriteKeys.add(key);
        if (action === "unfavorite") state.favoriteKeys.delete(key);
        if (action === "hide") state.hiddenKeys.add(key);
        if (action === "unhide") state.hiddenKeys.delete(key);
      }
      mirrorReadingState();
    }
    async function runLibraryAction(action, papers, message, event) {
      const items = (papers || []).filter(Boolean);
      if (!items.length) {
        toast("当前没有可处理条目");
        return;
      }
      let ok = true;
      if (items.some((paper) => aiDecisionForPaper(paper))) {
        for (const paper of items) {
          const itemOk = await applyLibraryActionClient(action, [paper], eventWithAiDecision(paper, event), { refreshPreference: false });
          ok = itemOk && ok;
          if (!itemOk) applyLocalLibraryAction(action, [paper]);
        }
        if (ok) await loadPreferenceState();
      } else {
        ok = await applyLibraryActionClient(action, items, event);
      }
      if (!ok) applyLocalLibraryAction(action, items);
      toast(`${message}${ok ? "" : "（本地 fallback）"}`);
      renderVisibleItems();
    }
    async function toggleRead(paper) {
      const key = paperReadingKey(paper);
      const action = state.readKeys.has(key) ? "unread" : "read";
      await runLibraryAction(action, [paper], action === "read" ? "已标记为已读" : "已标记为未读", { source: "daily_card" });
    }
    async function toggleFavorite(paper) {
      const key = paperReadingKey(paper);
      const action = state.favoriteKeys.has(key) ? "unfavorite" : "favorite";
      await runLibraryAction(action, [paper], action === "favorite" ? "已收藏" : "已取消收藏", { source: "daily_card" });
    }
    function toggleHideRead() {
      state.hideRead = !state.hideRead;
      state.page = 1;
      saveStoredBool(HIDE_READ_STORAGE_KEY, state.hideRead);
      renderVisibleItems();
    }
    function mergeUnique(left, right) {
      const out = [];
      const seen = new Set();
      for (const value of [...(left || []), ...(right || [])]) {
        const key = typeof value === "object" ? JSON.stringify(value) : String(value);
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(value);
      }
      return out;
    }
    function mergeDailyPaper(before, after) {
      return {
        ...after,
        ...before,
        abstract: before.abstract || after.abstract || "",
        pdf_url: before.pdf_url || after.pdf_url || "",
        doi: before.doi || after.doi || "",
        pmid: before.pmid || after.pmid || "",
        pmcid: before.pmcid || after.pmcid || "",
        openalex_id: before.openalex_id || after.openalex_id || "",
        citation_count: Math.max(before.citation_count ?? -1, after.citation_count ?? -1) >= 0
          ? Math.max(before.citation_count ?? -1, after.citation_count ?? -1)
          : null,
        authors: mergeUnique(before.authors, after.authors),
        categories: mergeUnique(before.categories, after.categories),
        concepts: mergeUnique(before.concepts, after.concepts),
        source_records: mergeUnique(before.source_records, after.source_records),
        _daily_sources: mergeUnique(before._daily_sources, after._daily_sources),
        _daily_source_records: mergeUnique(before._daily_source_records, after._daily_source_records),
        _canonical_key: before._canonical_key || after._canonical_key,
        _cache_date: String(before._cache_date || "") > String(after._cache_date || "") ? before._cache_date : after._cache_date,
      };
    }
    function baseVisibleItems() {
      let visible = (state.allItems || []).filter((paper) => !state.hiddenKeys.has(paperReadingKey(paper)));
      if (state.viewMode === "favorites") {
        visible = visible.filter((paper) => state.favoriteKeys.has(paperReadingKey(paper)));
      }
      if (!state.hideRead) return visible;
      return visible.filter((paper) => !state.readKeys.has(paperReadingKey(paper)));
    }
    function displayItems() {
      const visible = baseVisibleItems();
      if (!state.aiFilterActive) return visible;
      return visible
        .filter((paper) => state.aiFilterResults.has(paperReadingKey(paper)))
        .sort((a, b) => {
          const left = aiDecisionForPaper(a) || {};
          const right = aiDecisionForPaper(b) || {};
          const groupDelta = aiGroupOrder(aiDecisionGroup(left)) - aiGroupOrder(aiDecisionGroup(right));
          if (groupDelta) return groupDelta;
          return Number(right.importance || 0) - Number(left.importance || 0);
        });
    }
    function pruneSelectedKeys() {
      const known = new Set((state.allItems || []).map((paper) => paperReadingKey(paper)).filter(Boolean));
      for (const key of Array.from(state.selectedKeys)) {
        if (!known.has(key)) state.selectedKeys.delete(key);
      }
    }
    function renderVisibleItems(activeSources = state.lastActiveSources) {
      state.lastActiveSources = activeSources || 0;
      pruneSelectedKeys();
      const visible = displayItems();
      const maxPage = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
      if (state.page > maxPage) state.page = maxPage;
      const offset = state.aiFilterActive ? 0 : (state.page - 1) * PAGE_SIZE;
      state.hasMore = !state.aiFilterActive && visible.length > offset + PAGE_SIZE;
      state.currentItems = state.aiFilterActive ? visible : visible.slice(offset, offset + PAGE_SIZE);
      const hidden = state.hideRead ? `，隐藏已读 ${(state.allItems || []).length - visible.length} 条` : "";
      const aiCounts = state.aiFilterActive ? aiFilterCounts(visible) : null;
      const aiText = aiCounts ? `，AI筛选：推荐 ${aiCounts.recommend} / 待定 ${aiCounts.maybe} / 不建议 ${aiCounts.reject}` : "";
      const statusPrefix = state.viewMode === "favorites"
        ? `收藏夹 ${(state.allItems || []).length} 条`
        : `缓存 ${(state.allItems || []).length} 条 / ${state.lastActiveSources} 源`;
      $("resultStatus").textContent = `${statusPrefix}，显示 ${visible.length} 条，当前页 ${state.currentItems.length} 条${hidden}${aiText}`;
      renderPapers(state.currentItems);
      updateButtons();
    }
    function flattenDailyPayloads(payloads, query) {
      const byKey = new Map();
      state.sourceCounts = new Map();
      for (const payload of payloads) {
        for (const group of payload.groups || []) {
          const items = group.items || [];
          for (const item of items) {
            const paper = {
              ...item,
              _daily_date: item._cache_date || payload.date,
              _daily_source: group.source,
              _daily_source_display: group.display_name || group.source,
            };
            for (const sourceKey of (paper._daily_sources || [group.source])) {
              state.sourceCounts.set(sourceKey, (state.sourceCounts.get(sourceKey) || 0) + 1);
            }
            if (paperMatchesQuery(paper, query)) {
              const key = paperCanonicalKey(paper);
              byKey.set(key, byKey.has(key) ? mergeDailyPaper(byKey.get(key), paper) : paper);
            }
          }
        }
      }
      return Array.from(byKey.values()).sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")));
    }
