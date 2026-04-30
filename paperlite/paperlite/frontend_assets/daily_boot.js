    async function loadSources() {
      const payload = await fetchJson("/sources?format=json");
      state.sources = (payload.sources || []).sort((a, b) => {
        const ak = `${sourceKindOf(a)} ${a.category_label || ""} ${a.display_name || a.name}`;
        const bk = `${sourceKindOf(b)} ${b.category_label || ""} ${b.display_name || b.name}`;
        return ak.localeCompare(bk, "zh-CN");
      });
      const params = new URLSearchParams(window.location.search);
      const from = params.get("date_from");
      const to = params.get("date_to") || params.get("date");
      if (from) $("dateFrom").value = from;
      if (to) $("dateTo").value = to;
      const page = Number(params.get("page") || "1");
      state.page = Number.isFinite(page) && page > 0 ? page : 1;
      const q = params.get("q");
      if (q) $("search").value = q;
      const discipline = params.get("discipline");
      if (discipline) state.selectedDiscipline = discipline;
      const source = params.get("source");
      if (source) for (const item of source.split(",")) if (item.trim()) state.selectedSources.add(item.trim());
      updateButtons();
    }

    function changePage(delta) {
      if (delta < 0 && state.page <= 1) return;
      if (delta > 0 && !state.hasMore) return;
      state.page += delta;
      if (state.viewMode === "favorites") renderVisibleItems(0);
      else loadPapers();
    }

    function bindEvents() {
      $("apiBtn").addEventListener("click", () => { window.location.href = "/ops"; });
      $("searchBtn").addEventListener("click", () => { state.page = 1; loadPapers("搜索"); });
      $("translateBtn").addEventListener("click", () => translateCurrentPage());
      $("exportBtn").addEventListener("click", () => $("exportMenu").classList.toggle("open"));
      for (const button of $("exportMenu").querySelectorAll("[data-export-format]")) {
        button.addEventListener("click", () => exportCurrentResults(button.dataset.exportFormat));
      }
      $("dailyViewBtn").addEventListener("click", () => { state.page = 1; loadPapers("全部缓存"); });
      $("favoritesViewBtn").addEventListener("click", () => loadFavoriteShelf());
      $("refreshBtn").addEventListener("click", () => loadPapers("刷新"));
      $("crawlBtn").addEventListener("click", () => { state.page = 1; startCrawl(); });
      $("scheduleBtn").addEventListener("click", () => startSchedule());
      $("todayBtn").addEventListener("click", () => { today(); state.page = 1; loadPapers(); });
      $("weekBtn").addEventListener("click", () => { thisWeek(); state.page = 1; loadPapers(); });
      $("prevBtn").addEventListener("click", () => changePage(-1));
      $("nextBtn").addEventListener("click", () => changePage(1));
      $("hideReadBtn").addEventListener("click", () => toggleHideRead());
      $("batchReadBtn").addEventListener("click", () => batchLibraryAction("read", "已批量标记为已读"));
      $("batchFavoriteBtn").addEventListener("click", () => batchLibraryAction("favorite", "已批量收藏"));
      $("batchHideBtn").addEventListener("click", () => batchLibraryAction("hide", "已批量隐藏"));
      $("batchTranslateBtn").addEventListener("click", () => translateBatch());
      $("batchEnrichBtn").addEventListener("click", () => enrichBatch());
      $("batchZoteroBtn").addEventListener("click", () => zoteroBatch());
      $("aiFilterBtn").addEventListener("click", () => runAiFilter());
      $("clearAiFilterBtn").addEventListener("click", () => clearAiFilter());
      $("aiFilterQuery").addEventListener("input", () => updateButtons());
      $("ragIndexBtn").addEventListener("click", () => runRagIndex());
      $("ragAskBtn").addEventListener("click", () => runRagAsk());
      $("clearRagBtn").addEventListener("click", () => clearRagResult());
      $("ragQuestion").addEventListener("input", () => updateButtons());
      $("ragTopK").addEventListener("input", () => updateButtons());
      $("ragQuestion").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) runRagAsk();
      });
      $("learningEnabled").addEventListener("change", (event) => updatePreferenceSettings({ learning_enabled: Boolean(event.target.checked) }));
      $("clearLearningDataBtn").addEventListener("click", () => clearLearningData());
      $("saveViewBtn").addEventListener("click", () => saveCurrentView());
      $("loadViewBtn").addEventListener("click", () => loadSelectedView());
      $("deleteViewBtn").addEventListener("click", () => deleteSelectedView());
      $("savedViewSelect").addEventListener("change", () => {
        const view = state.savedViews.find((item) => item.view_id === $("savedViewSelect").value);
        if (view) $("viewName").value = view.name;
      });
      $("search").addEventListener("keydown", (event) => {
        if (event.key === "Enter") { state.page = 1; loadPapers("搜索"); }
      });
      $("dateFrom").addEventListener("change", () => { state.page = 1; loadPapers(); });
      $("dateTo").addEventListener("change", () => { state.page = 1; loadPapers(); });
      $("disciplineBtn").addEventListener("click", () => openSourcePicker("discipline"));
      $("sourceBtn").addEventListener("click", () => openSourcePicker("source"));
      $("sourceSearch").addEventListener("input", () => {
        state.sourceQuery = $("sourceSearch").value;
        state.sourceRenderCount = 120;
        if (state.pickerMode === "discipline") renderDisciplinePicker();
        else renderSourcePicker();
      });
      $("selectedOnlyBtn").addEventListener("click", () => {
        state.selectedOnly = !state.selectedOnly;
        $("selectedOnlyBtn").classList.toggle("dark", state.selectedOnly);
        if (state.pickerMode === "discipline") renderDisciplinePicker();
        else renderSourcePicker();
      });
      $("clearSourcesBtn").addEventListener("click", () => {
        state.selectedSources.clear();
        state.selectedDiscipline = "";
        updateButtons();
        if (state.pickerMode === "discipline") renderDisciplinePicker();
        else renderSourcePicker();
        state.page = 1;
        loadPapers();
      });
      $("doneSourcesBtn").addEventListener("click", () => {
        $("sourcePopover").classList.remove("open");
        state.page = 1;
        loadPapers();
      });
      document.addEventListener("pointerdown", (event) => {
        if (!$("exportWrap").contains(event.target)) $("exportMenu").classList.remove("open");
        const pop = $("sourcePopover");
        if (!pop.classList.contains("open")) return;
        if (pop.contains(event.target) || $("sourceBtn").contains(event.target) || $("disciplineBtn").contains(event.target)) return;
        pop.classList.remove("open");
      });
    }

    async function boot() {
      initReadingState();
      initPreferenceState();
      today();
      bindEvents();
      try {
        await loadSources();
      } catch (error) {
        toast(`来源加载失败：${error.message}`);
      }
      await loadSavedViews();
      await loadPreferenceState();
      await loadPapers();
    }
    boot();
