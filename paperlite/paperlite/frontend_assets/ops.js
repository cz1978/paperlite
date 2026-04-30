    const $ = (id) => document.getElementById(id);
    let auditIssuesOnly = false;
    let lastAuditPayload = null;
    let lastAuditNextOffset = null;
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    }
    function statusTone(status) {
      if (["completed", "ok", "active"].includes(status)) return "ok";
      if (["queued", "running", "paused", "candidate", "timeout", "warn"].includes(status)) return "warn";
      if (["failed", "fail", "dead_404", "blocked_403", "html_not_feed", "tls_error", "request_error"].includes(status)) return "bad";
      return "";
    }
    function shortTime(value) {
      if (!value) return "-";
      return String(value).replace("T", " ").replace("+00:00", "Z");
    }
    function renderMetrics(data) {
      const summary = data.catalog_summary || {};
      const scheduler = data.scheduler || {};
      const health = data.health_snapshot || {};
      const doctor = data.doctor || {};
      const cache = data.cache_summary || {};
      const run = data.run_summary || {};
      const schedule = data.schedule_summary || {};
      const audit = data.source_audit_summary || {};
      const nextSchedule = schedule.next_active_schedule || {};
      const doctorSource = doctor.snapshot_source ? `snapshot ${doctor.snapshot_source}` : "snapshot";
      $("metrics").innerHTML = [
        ["Doctor", String(doctor.overall || "-").toUpperCase(), `${doctor.fail || 0} fail · ${doctor.warn || 0} warn · ${doctorSource}`],
        ["缓存论文", `${cache.cache_item_count || 0}`, cache.latest_cache_date || "-"],
        ["失败源", `${run.failed_source_count || 0}`, run.latest_duration_seconds != null ? `latest ${run.latest_duration_seconds}s` : "no finished run"],
        ["内容体检", `${audit.problem_count || 0}`, audit.loaded ? `${audit.checked_count || 0} checked` : "未运行"],
        ["下次定时", nextSchedule.next_run_at ? shortTime(nextSchedule.next_run_at) : "-", `${schedule.paused_count || 0} paused`],
        ["最近错误", `${(data.recent_errors || []).length}`, "runs / sources / schedules"],
        ["活跃定时", `${schedule.active_count || 0}`, scheduler.enabled ? `scheduler on / ${scheduler.poll_seconds}s` : "scheduler off"],
        ["来源总数", `${summary.source_count || 0}`, `${summary.endpoint_count || 0} endpoints`],
        ["健康快照", health.loaded ? "已加载" : "未加载", health.age_seconds != null ? `${health.age_seconds}s ago` : (health.checked_at_max || health.path || "-")],
      ].map(([label, value, sub]) => `
        <div class="metric">
          <div class="metric-value">${escapeHtml(value)}</div>
          <div class="metric-label">${escapeHtml(label)}</div>
          <div class="hint">${escapeHtml(sub)}</div>
        </div>
      `).join("");
    }
    function renderRuntimeSummary(data) {
      const cache = data.cache_summary || {};
      const run = data.run_summary || {};
      const schedule = data.schedule_summary || {};
      const health = data.health_snapshot || {};
      const audit = data.source_audit_summary || {};
      const errors = data.recent_errors || [];
      const next = schedule.next_active_schedule || {};
      const errorsHtml = errors.length ? errors.map((item) => `
        <div class="row">
          <div class="row-title"><span class="badge bad">${escapeHtml(item.kind)}</span>${escapeHtml(item.id || "-")}</div>
          <div class="meta">${escapeHtml(shortTime(item.at))}</div>
          <div class="error">${escapeHtml(item.message || "")}</div>
          <div></div>
          <div></div>
        </div>
      `).join("") : `<div class="empty">最近没有记录到错误。</div>`;
      $("runtimeSummary").innerHTML = `
        <div class="health-grid">
          <span class="badge">DB ${escapeHtml(cache.db_path || "-")}</span>
          <span class="badge">daily_entries ${escapeHtml(cache.daily_entry_count || 0)}</span>
          <span class="badge">latest_cache ${escapeHtml(cache.latest_cache_date || "-")}</span>
          <span class="badge">latest_duration ${escapeHtml(run.latest_duration_seconds ?? "-")}s</span>
          <span class="badge ${Number(run.failed_source_count || 0) ? "bad" : "ok"}">failed_sources ${escapeHtml(run.failed_source_count || 0)}</span>
          <span class="badge">next_schedule ${escapeHtml(next.next_run_at ? shortTime(next.next_run_at) : "-")}</span>
          <span class="badge ${Number(schedule.paused_count || 0) ? "warn" : "ok"}">paused ${escapeHtml(schedule.paused_count || 0)}</span>
          <span class="badge">health_age ${escapeHtml(health.age_seconds ?? "-")}s</span>
          <span class="badge ${Number(audit.fail || 0) ? "bad" : (Number(audit.warn || 0) ? "warn" : "ok")}">source_audit ${escapeHtml(audit.ok || 0)}/${escapeHtml(audit.warn || 0)}/${escapeHtml(audit.fail || 0)}</span>
        </div>
        <div style="height:10px"></div>
        ${errorsHtml}
      `;
    }
    function renderRuns(runs) {
      if (!runs.length) {
        $("runs").innerHTML = `<div class="empty">还没有抓取任务。回到每日流，选学科后点抓取。</div>`;
        return;
      }
      $("runs").innerHTML = runs.map((run) => {
        const sourceResults = run.source_results || [];
        const failed = sourceResults.filter((item) => item.error).length;
        const warnings = (run.warnings || []).slice(0, 3).join("；");
        return `
          <div class="row">
            <div>
              <div class="row-title"><span class="badge ${statusTone(run.status)}">${escapeHtml(run.status)}</span>${escapeHtml(run.discipline_key)}</div>
              <div class="meta">${escapeHtml(run.date_from)} 至 ${escapeHtml(run.date_to)} · ${escapeHtml(run.run_id)}</div>
            </div>
            <div class="meta">${escapeHtml(shortTime(run.started_at))}<br>${escapeHtml(shortTime(run.finished_at))}</div>
            <div><strong>${escapeHtml(run.total_items || 0)}</strong> 条<br><span class="meta">${(run.source_keys || []).length} 源</span></div>
            <div class="meta">${sourceResults.length} endpoint${failed ? ` · ${failed} 失败` : ""}</div>
            <div class="${run.error ? "error" : "meta"}">${escapeHtml(run.error || warnings || "")}</div>
          </div>
        `;
      }).join("");
    }
    function renderSchedules(schedules) {
      if (!schedules.length) {
        $("schedules").innerHTML = `<div class="empty">还没有定时任务。回到每日流，选学科后点定时。</div>`;
        return;
      }
      $("schedules").innerHTML = schedules.map((schedule) => {
        const next = schedule.status === "paused" ? "已暂停" : shortTime(schedule.next_run_at);
        const action = schedule.status === "paused" ? "active" : "paused";
        const label = schedule.status === "paused" ? "恢复" : "暂停";
        return `
          <div class="row">
            <div>
              <div class="row-title"><span class="badge ${statusTone(schedule.status)}">${escapeHtml(schedule.status)}</span>${escapeHtml(schedule.discipline_key)}</div>
              <div class="meta">${(schedule.source_keys || []).length} 源 · lookback ${schedule.lookback_days} 天</div>
            </div>
            <div class="meta">每 ${escapeHtml(schedule.interval_minutes)} 分钟<br>limit ${escapeHtml(schedule.limit_per_source)}</div>
            <div class="meta">下次<br>${escapeHtml(next)}</div>
            <div class="meta">上次<br>${escapeHtml(shortTime(schedule.last_finished_at || schedule.last_started_at))}</div>
            <div class="actions">
              <button class="btn tiny" data-action="schedule-status" data-id="${escapeHtml(schedule.schedule_id)}" data-status="${action}" type="button">${label}</button>
              <button class="btn tiny" data-action="schedule-delete" data-id="${escapeHtml(schedule.schedule_id)}" type="button">删除</button>
            </div>
          </div>
          ${schedule.error ? `<div class="error">${escapeHtml(schedule.error)}</div>` : ""}
        `;
      }).join("");
    }
    function compactCounts(counts) {
      const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 4);
      return entries.length ? entries.map(([key, value]) => `${key}:${value}`).join(" · ") : "-";
    }
    function renderCoverage(data) {
      const coverage = data.catalog_coverage || {};
      const totals = coverage.totals || {};
      const rows = (coverage.disciplines || [])
        .filter((item) => Number(item.source_count || 0) > 0)
        .sort((a, b) => Number(b.source_count || 0) - Number(a.source_count || 0))
        .slice(0, 14);
      const rowsHtml = rows.length ? rows.map((item) => `
        <div class="row">
          <div>
            <div class="row-title">${escapeHtml(item.label || item.key)}</div>
            <div class="meta">${escapeHtml(item.key)} · ${escapeHtml(item.area_label || item.area_key || "")}</div>
          </div>
          <div><strong>${escapeHtml(item.source_count || 0)}</strong> 源<br><span class="meta">${escapeHtml(compactCounts(item.source_kind_counts))}</span></div>
          <div><span class="badge ok">可抓 ${escapeHtml(item.runnable_source_count || 0)}</span></div>
          <div><span class="badge ${Number(item.unavailable_source_count || 0) ? "bad" : "ok"}">不可用 ${escapeHtml(item.unavailable_source_count || 0)}</span></div>
          <div class="meta">${escapeHtml(compactCounts(item.health_status_counts))}</div>
        </div>
      `).join("") : `<div class="empty">目录里还没有可展示的学科覆盖数据。</div>`;
      $("coverage").innerHTML = `
        <div class="health-grid">
          <span class="badge">总源 ${escapeHtml(totals.source_count || 0)}</span>
          <span class="badge ok">可抓 ${escapeHtml(totals.runnable_source_count || 0)}</span>
          <span class="badge ok">健康 ${escapeHtml(totals.healthy_source_count || 0)}</span>
          <span class="badge ${Number(totals.unavailable_source_count || 0) ? "bad" : "ok"}">不可用 ${escapeHtml(totals.unavailable_source_count || 0)}</span>
        </div>
        <div class="hint">${escapeHtml(coverage.general_policy || "")}</div>
        <div style="height:10px"></div>
        ${rowsHtml}
      `;
    }
    function renderHealth(data, checked) {
      const summary = data.catalog_summary || {};
      const health = data.health_snapshot || {};
      const counts = summary.health_status_counts || {};
      const unavailable = data.unavailable_sources || [];
      const countHtml = Object.keys(counts).sort().map((key) => `
        <span class="badge ${statusTone(key)}">${escapeHtml(key)} ${escapeHtml(counts[key])}</span>
      `).join("");
      const unavailableHtml = unavailable.length
        ? unavailable.map((item) => `
            <div class="row">
              <div class="row-title">${escapeHtml(item.display_name || item.name)}</div>
              <div class="meta">${escapeHtml(item.name)}</div>
              <div><span class="badge ${statusTone(item.health_status)}">${escapeHtml(item.health_status)}</span></div>
              <div class="meta">${escapeHtml(item.primary_discipline_label || "")}</div>
              <div class="meta">${escapeHtml(item.quality_status || "")}</div>
            </div>
          `).join("")
        : `<div class="empty">当前没有健康快照标记的不可用来源。</div>`;
      $("health").innerHTML = `
        <div class="health-grid">${countHtml || '<span class="badge">无快照</span>'}</div>
        <div class="hint">快照：${escapeHtml(health.loaded ? "已加载" : "未加载")} · ${escapeHtml(health.checked_at_max || health.path || "-")}</div>
        ${checked ? `<div class="hint">刚检测：${escapeHtml(checked.updated || 0)} 个 endpoint，快照共 ${escapeHtml(checked.count || 0)} 条。</div>` : ""}
        <div style="height:10px"></div>
        ${unavailableHtml}
      `;
    }
    function renderSourceAudit(data, auditPayload, checked) {
      const summary = (checked && checked.summary) || (auditPayload && auditPayload.summary) || data.source_audit_summary || {};
      const rows = ((checked && checked.results) || (auditPayload && (auditPayload.audit || auditPayload.results)) || []);
      lastAuditPayload = checked || auditPayload || null;
      if (checked && checked.next_offset !== undefined) lastAuditNextOffset = checked.next_offset;
      const issueCounts = summary.issue_counts || {};
      const countHtml = Object.keys(issueCounts).sort().map((key) => `
        <span class="badge warn">${escapeHtml(key)} ${escapeHtml(issueCounts[key])}</span>
      `).join("");
      const visibleRows = (auditIssuesOnly ? rows.filter((item) => item.status !== "ok") : rows).slice(0, 30);
      const rowsHtml = visibleRows.length
        ? visibleRows.map((item) => `
            <div class="row">
              <div>
                <div class="row-title"><span class="badge ${statusTone(item.status)}">${escapeHtml(item.status)}</span>${escapeHtml(item.endpoint_key || "-")}</div>
                <div class="meta">${escapeHtml(item.source_name || item.source_key || "")}</div>
              </div>
              <div class="meta">${escapeHtml(item.source_key || "")}<br>${escapeHtml(item.endpoint_mode || "")}</div>
              <div><strong>${escapeHtml(item.item_count ?? 0)}</strong> 条<br><span class="meta">抽样 ${escapeHtml(item.requested_sample_size || 0)}</span></div>
              <div class="meta">${escapeHtml((item.issue_tags || []).join(" / ") || "字段正常")}</div>
              <div class="${item.status === "fail" ? "error" : "meta"}">${escapeHtml(item.message || "")}</div>
            </div>
          `).join("")
        : `<div class="empty">${auditIssuesOnly ? "当前没有问题源。" : "还没有来源内容体检快照。点“检查一批”开始。"}</div>`;
      $("sourceAudit").innerHTML = `
        <div class="health-grid">
          <span class="badge">已检 ${escapeHtml(summary.checked_count || checked?.checked || 0)}</span>
          <span class="badge ok">ok ${escapeHtml(summary.ok || 0)}</span>
          <span class="badge warn">warn ${escapeHtml(summary.warn || 0)}</span>
          <span class="badge bad">fail ${escapeHtml(summary.fail || 0)}</span>
          <span class="badge">问题源 ${escapeHtml(summary.problem_count || 0)}</span>
          ${countHtml}
        </div>
        <div class="hint">快照：${escapeHtml(auditPayload?.loaded ? "已加载" : "未加载")} · ${escapeHtml(auditPayload?.updated_at || data.source_audit_summary?.updated_at || "-")}</div>
        ${checked ? `<div class="hint">刚体检：${escapeHtml(checked.checked || 0)} 个 endpoint，next_offset ${escapeHtml(checked.next_offset ?? "-")}。</div>` : ""}
        <div style="height:10px"></div>
        ${rowsHtml}
      `;
    }
    async function loadStatus() {
      const data = await fetchJson("/ops/status?limit=20");
      const audit = await fetchJson("/ops/source-audit");
      renderMetrics(data);
      renderRuntimeSummary(data);
      renderRuns(data.recent_runs || []);
      renderSchedules(data.schedules || []);
      renderCoverage(data);
      renderHealth(data);
      renderSourceAudit(data, audit);
    }
    async function updateSchedule(id, status) {
      await fetchJson(`/daily/schedules/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await loadStatus();
    }
    async function deleteSchedule(id) {
      await fetchJson(`/daily/schedules/${encodeURIComponent(id)}`, { method: "DELETE" });
      await loadStatus();
    }
    async function checkHealth() {
      $("healthCheckBtn").disabled = true;
      $("healthHint").textContent = "正在检测选中的 endpoint...";
      try {
        const payload = {
          discipline: $("healthDiscipline").value.trim() || null,
          source: $("healthSource").value.trim() || null,
          mode: $("healthMode").value || null,
          limit: Number.parseInt($("healthLimit").value, 10) || 50,
          timeout_seconds: Number.parseFloat($("healthTimeout").value) || 5,
        };
        const checked = await fetchJson("/ops/health/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await fetchJson("/ops/status?limit=20");
        renderMetrics(data);
        renderHealth(data, checked.snapshot);
        $("healthHint").textContent = `检测完成：${checked.checked} 个 endpoint`;
      } catch (error) {
        $("healthHint").textContent = `检测失败：${error.message}`;
      } finally {
        $("healthCheckBtn").disabled = false;
      }
    }
    function auditPayload(offsetOverride) {
      return {
        discipline: $("auditDiscipline").value.trim() || null,
        source: $("auditSource").value.trim() || null,
        mode: $("auditMode").value || null,
        limit: Number.parseInt($("auditLimit").value, 10) || 100,
        offset: offsetOverride ?? (Number.parseInt($("auditOffset").value, 10) || 0),
        sample_size: Number.parseInt($("auditSampleSize").value, 10) || 3,
        timeout_seconds: Number.parseFloat($("auditTimeout").value) || 5,
      };
    }
    async function checkSourceAudit(offsetOverride) {
      $("auditCheckBtn").disabled = true;
      $("auditNextBtn").disabled = true;
      $("auditHint").textContent = "正在抽样体检来源元数据...";
      try {
        const checked = await fetchJson("/ops/source-audit/check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(auditPayload(offsetOverride)),
        });
        if (checked.next_offset != null) $("auditOffset").value = String(checked.next_offset);
        const data = await fetchJson("/ops/status?limit=20");
        const audit = await fetchJson("/ops/source-audit");
        renderMetrics(data);
        renderRuntimeSummary(data);
        renderSourceAudit(data, audit, checked);
        $("auditHint").textContent = `体检完成：${checked.checked} 个 endpoint；不会自动继续跑。`;
      } catch (error) {
        $("auditHint").textContent = `体检失败：${error.message}`;
      } finally {
        $("auditCheckBtn").disabled = false;
        $("auditNextBtn").disabled = false;
      }
    }
    document.addEventListener("click", (event) => {
      const target = event.target.closest("button");
      if (!target) return;
      if (target.dataset.action === "schedule-status") updateSchedule(target.dataset.id, target.dataset.status);
      if (target.dataset.action === "schedule-delete") deleteSchedule(target.dataset.id);
    });
    $("healthCheckBtn").addEventListener("click", checkHealth);
    $("auditCheckBtn").addEventListener("click", () => checkSourceAudit());
    $("auditNextBtn").addEventListener("click", () => checkSourceAudit(lastAuditNextOffset ?? (Number.parseInt($("auditOffset").value, 10) || 0)));
    $("auditIssuesBtn").addEventListener("click", () => {
      auditIssuesOnly = !auditIssuesOnly;
      $("auditIssuesBtn").textContent = auditIssuesOnly ? "显示全部源" : "只看问题源";
      fetchJson("/ops/status?limit=20")
        .then((data) => renderSourceAudit(data, lastAuditPayload || {}, null))
        .catch(() => {});
    });
    loadStatus().catch((error) => {
      $("metrics").innerHTML = `<div class="empty error">运行状态加载失败：${escapeHtml(error.message)}</div>`;
    });
