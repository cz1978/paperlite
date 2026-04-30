    function profileSignalCounts() {
      return state.preferenceProfile?.signal_counts || state.preferenceProfile?.profile?.signal_counts || {};
    }
    function profileSettings() {
      return state.preferenceSettings || state.preferenceProfile?.profile?.settings || {};
    }
    function renderPreferenceControls() {
      const counts = profileSignalCounts();
      const updated = state.preferenceProfile?.updated_at || state.preferenceProfile?.generated_at || "未生成";
      const promptCount = Number(counts.enabled_prompt_count || 0);
      const queryCount = Number(counts.query_count || 0);
      const favoriteCount = Number(counts.favorite_count || 0);
      const readCount = Number(counts.read_count || 0);
      const hiddenCount = Number(counts.hidden_count || 0);
      const settings = profileSettings();
      const learningMode = settings.learning_enabled ? "学习开启" : "学习关闭";
      $("preferenceStatus").textContent = `${learningMode} · 长期提示词 ${promptCount} · 手动筛选词 ${queryCount} · 收藏 ${favoriteCount} · 已读 ${readCount} · 隐藏 ${hiddenCount} · ${updated}`;
      updateButtons();
    }
    async function loadPreferenceState() {
      try {
        const [profile, settings] = await Promise.all([
          fetchJson("/preferences/profile"),
          fetchJson("/preferences/settings"),
        ]);
        state.preferenceProfile = profile;
        state.preferenceSettings = settings.settings || state.preferenceSettings;
      } catch (_) {
        state.preferenceProfile = null;
        $("preferenceStatus").textContent = "偏好 API 不可用";
        updateButtons();
        return;
      }
      renderPreferenceControls();
    }
    async function updatePreferenceSettings(updates) {
      state.preferenceInFlight = true;
      updateButtons();
      try {
        const payload = await fetchJson("/preferences/settings", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ settings: updates }),
        });
        state.preferenceSettings = payload.settings || state.preferenceSettings;
        await loadPreferenceState();
        toast(state.preferenceSettings.learning_enabled ? "自我学习已开启" : "自我学习已关闭");
      } catch (error) {
        toast(`更新自我学习失败：${error.message}`);
      } finally {
        state.preferenceInFlight = false;
        updateButtons();
      }
    }
    async function clearLearningData() {
      state.preferenceInFlight = true;
      updateButtons();
      try {
        const payload = await fetchJson("/preferences/learning-data/clear", { method: "POST" });
        state.preferenceProfile = payload.profile || state.preferenceProfile;
        renderPreferenceControls();
        toast(`学习数据已清理：筛选词 ${payload.removed_queries || 0}，行为信号 ${payload.removed_events || 0}`);
      } catch (error) {
        toast(`清理学习数据失败：${error.message}`);
      } finally {
        state.preferenceInFlight = false;
        updateButtons();
      }
    }

    function currentViewFilters() {
      return {
        date_from: $("dateFrom").value,
        date_to: $("dateTo").value,
        discipline: state.selectedDiscipline,
        sources: Array.from(state.selectedSources),
        q: $("search").value.trim(),
        hide_read: state.hideRead,
      };
    }
    function renderSavedViews() {
      const selected = $("savedViewSelect").value;
      $("savedViewSelect").innerHTML = `<option value="">加载视图</option>${state.savedViews.map((view) => `
        <option value="${escapeHtml(view.view_id)}">${escapeHtml(view.name)}</option>
      `).join("")}`;
      if (selected) $("savedViewSelect").value = selected;
    }
    async function loadSavedViews() {
      try {
        const payload = await fetchJson("/library/views");
        state.savedViews = payload.views || [];
        renderSavedViews();
      } catch (_) {
        state.savedViews = [];
        renderSavedViews();
      }
    }
    async function saveCurrentView() {
      const name = $("viewName").value.trim();
      if (!name) {
        toast("先填写视图名称");
        return;
      }
      try {
        const view = await fetchJson("/library/views", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, filters: currentViewFilters() }),
        });
        $("viewName").value = view.name;
        await loadSavedViews();
        $("savedViewSelect").value = view.view_id;
        toast("视图已保存");
      } catch (error) {
        toast(`保存视图失败：${error.message}`);
      }
    }
    function applySavedView(view) {
      const filters = view?.filters || {};
      if (filters.date_from) $("dateFrom").value = filters.date_from;
      if (filters.date_to) $("dateTo").value = filters.date_to;
      $("search").value = filters.q || "";
      state.selectedDiscipline = filters.discipline || "";
      state.selectedSources = new Set(Array.isArray(filters.sources) ? filters.sources.filter(Boolean).map(String) : []);
      state.hideRead = Boolean(filters.hide_read);
      $("viewName").value = view.name || "";
      state.page = 1;
      saveStoredBool(HIDE_READ_STORAGE_KEY, state.hideRead);
      updateButtons();
    }
    async function loadSelectedView() {
      const view = state.savedViews.find((item) => item.view_id === $("savedViewSelect").value);
      if (!view) {
        toast("先选择一个视图");
        return;
      }
      applySavedView(view);
      await loadPapers("加载视图");
    }
    async function deleteSelectedView() {
      const view = state.savedViews.find((item) => item.view_id === $("savedViewSelect").value);
      if (!view) {
        toast("先选择一个视图");
        return;
      }
      try {
        await fetchJson(`/library/views?view_id=${encodeURIComponent(view.view_id)}`, { method: "DELETE" });
        $("viewName").value = "";
        await loadSavedViews();
        toast("视图已删除");
      } catch (error) {
        toast(`删除视图失败：${error.message}`);
      }
    }
