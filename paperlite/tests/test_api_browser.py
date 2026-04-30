from datetime import datetime

from fastapi.testclient import TestClient

from paperlite import api
from paperlite.ai_filter import DEFAULT_AI_FILTER_QUERY
from paperlite.models import Paper


def make_paper(id="arxiv:1", title="A readable paper", day=2):
    return Paper(
        id=id,
        source=id.split(":", 1)[0],
        source_type="preprint",
        title=title,
        abstract="A useful abstract.",
        authors=["Ada Lovelace"],
        url=f"https://example.com/{id}",
        pdf_url=f"https://example.com/{id}.pdf",
        doi="10.48550/arxiv.1",
        published_at=datetime(2024, 1, day),
        categories=["cs.LG"],
    )


def test_home_returns_paperlite_daily_ui():
    client = TestClient(api.create_app(), follow_redirects=False)

    response = client.get("/")

    assert response.status_code == 200
    assert "PaperLite" in response.text
    assert "每日学术流" in response.text
    assert 'id="sourcePopover"' in response.text


def test_daily_returns_html_by_default():
    client = TestClient(api.create_app())

    response = client.get("/daily")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PaperLite" in response.text
    assert "function safeExternalUrl" in response.text
    assert "new URL(raw)" in response.text
    assert '["http:", "https:"]' in response.text
    assert 'rel="noreferrer noopener"' in response.text
    assert "externalLink(paper.url" in response.text
    assert "externalLink(paper.pdf_url" in response.text
    assert "externalLink(paper.openalex_id" in response.text
    assert 'href="${escapeHtml(paper.url)}"' not in response.text
    assert 'href="${escapeHtml(paper.pdf_url)}"' not in response.text
    assert 'href="${escapeHtml(paper.openalex_id)}"' not in response.text
    assert "每日学术流" in response.text
    assert "搜索标题 / 摘要 / 来源" in response.text
    assert "运行" in response.text
    assert "/ops" in response.text
    assert "翻译" in response.text
    assert "导出" in response.text
    assert "抓取" in response.text
    assert "定时" in response.text
    assert "学科：全部" in response.text
    assert "来源：全部" in response.text
    assert "今天内容" in response.text
    assert "Zotero" in response.text
    assert "补全" in response.text
    assert "单条发送到 Zotero；未配置时导出 RIS；发送失败时询问是否导出 RIS" in response.text
    assert "单条元数据补全：OpenAlex / Crossref / PubMed / Europe PMC" in response.text
    assert "/daily/cache" in response.text
    assert "/daily/export" in response.text
    assert "/daily/crawl" in response.text
    assert "/daily/related" in response.text
    assert "/daily/schedules" in response.text
    assert "/agent/translate" in response.text
    assert "/agent/filter" in response.text
    assert "/agent/rag/index" in response.text
    assert "/agent/ask" in response.text
    assert "缓存问答" in response.text
    assert 'id="ragQuestion"' in response.text
    assert 'id="ragTopK"' in response.text
    assert 'id="ragIndexBtn"' in response.text
    assert 'id="ragAskBtn"' in response.text
    assert 'id="clearRagBtn"' in response.text
    assert 'id="ragResultPanel"' in response.text
    assert "indexRagScope" in response.text
    assert "askRagScope" in response.text
    assert "runRagIndex" in response.text
    assert "runRagAsk" in response.text
    assert "renderRagResult" in response.text
    assert "ragScopePayload" in response.text
    assert "payload.q = q" in response.text
    assert 'params.set("q", q)' in response.text
    assert "问当前筛选范围 metadata" in response.text
    assert "当前筛选范围为空，无法索引" in response.text
    assert "当前筛选范围为空，无法问答" in response.text
    assert "await runRagIndex" not in response.text
    assert "await runRagAsk" not in response.text
    assert "相关论文" in response.text
    assert "fetchRelatedPapers" in response.text
    assert "renderRelatedPapers" in response.text
    assert "loadRelatedPapers" in response.text
    assert "relatedScopeParams" in response.text
    assert "relatedPapers: new Map()" in response.text
    assert "await loadRelatedPapers" not in response.text
    assert "本地缓存" in response.text
    assert "抓取必须先选学科" in response.text
    assert "不会全量请求 800+ 源" in response.text
    assert "每隔多少分钟自动抓取当前学科/来源" in response.text
    assert "翻译当前页；多条按 1 秒间隔串行请求" in response.text
    assert "TRANSLATE_BATCH_DELAY_MS" in response.text
    assert "TRANSLATE_RETRY_BASE_MS" in response.text
    assert "TRANSLATE_MAX_RETRIES" in response.text
    assert "shouldRetryTranslate" in response.text
    assert "translatePaperWithThrottle" in response.text
    assert "translateCurrentPage" in response.text
    assert "LLM 限流/繁忙" in response.text
    assert "paperIdentifierLabel" in response.text
    assert "arxivIdentifier" in response.text
    assert "arXiv ${arxivId" in response.text
    assert "AI筛选" in response.text
    assert 'id="aiFilterQuery"' in response.text
    assert "AI筛选要求（可留空用默认标准）" in response.text
    assert "DEFAULT_AI_FILTER_LABEL" in response.text
    assert "默认学术价值筛选" in response.text
    assert "自我学习" in response.text
    assert 'id="learningEnabled"' in response.text
    assert 'id="clearLearningDataBtn"' in response.text
    assert "/preferences/profile" in response.text
    assert "/preferences/settings" in response.text
    assert "/preferences/learning-data/clear" in response.text
    assert "loadPreferenceState" in response.text
    assert "clearLearningData" in response.text
    assert "use_profile" in response.text
    assert "手动筛选词" in response.text
    assert "recordAiFilterSignals" in response.text
    assert "ai_recommend" in response.text
    assert "ai_reject" in response.text
    assert "aiDecisionEvent" in response.text
    assert "ai_decision" in response.text
    assert "quality_score" in response.text
    assert "preference_score" in response.text
    assert "质量 ${quality}/100" in response.text
    assert "偏好 ${preference}/100" in response.text
    assert "噪音 ${decision.noise_tags" in response.text
    assert "AI筛选使用个人画像" not in response.text
    assert 'id="usePreferenceProfile"' not in response.text
    assert 'id="preferencePromptInput"' not in response.text
    assert 'id="modelSignalLearning"' not in response.text
    assert 'id="autoPurifyEnabled"' not in response.text
    assert 'id="purifyPreferenceBtn"' not in response.text
    assert "自我净化" not in response.text
    assert "模型辅助学习" not in response.text
    assert "purifyPreferenceSignals" not in response.text
    assert 'id="aiFilterMode"' in response.text
    assert 'id="aiFilterScanLimit"' in response.text
    assert 'id="aiFilterKeepCount"' in response.text
    assert 'id="aiFilterThreshold"' in response.text
    assert "最多筛多少条" in response.text
    assert "推荐几条" in response.text
    assert "多重要才推荐" in response.text
    assert "控制请求量" in response.text
    assert "按数量" in response.text
    assert "按重要度" in response.text
    assert "推荐组" in response.text
    assert "待定组" in response.text
    assert "不建议组" in response.text
    assert "AI_FILTER_BATCH_DELAY_MS" in response.text
    assert "filterPaperWithThrottle" in response.text
    assert "baseVisibleItems" in response.text
    assert "翻译详情" in response.text
    assert "translateSinglePaper" in response.text
    assert "detailTranslationInFlightIds" in response.text
    assert "detailTranslations" in response.text
    assert "详情直译" in response.text
    assert 'translatePaperWithThrottle(paper, "detail")' in response.text
    assert "detail-tools" in response.text
    assert "detail-action" in response.text
    assert 'data-action="translate-detail"' in response.text
    assert "disciplineAliases" in response.text
    assert "工学" in response.text
    assert "pickerMode" in response.text
    assert 'state.pickerMode === "discipline"' in response.text
    assert "sourceDone = (run.source_results || []).length" in response.text
    assert "crawlWarningLabel" in response.text
    assert "crawlIssueItems" in response.text
    assert "crawlIssueSummary" in response.text
    assert "抓取完成但没有入库" in response.text
    assert "来源警告" in response.text
    assert "所选日期/来源没有匹配元数据" in response.text
    assert "Brief 翻译" in response.text
    assert "translation-bullets" in response.text
    assert "cn_flash_180" in response.text
    assert "card_bullets" in response.text
    assert "原始记录无摘要，仅跳过摘要 brief。" in response.text
    assert "abstract_missing" in response.text
    assert "cleanAbstractText" in response.text
    assert "htmlToPlainText" in response.text
    assert "decodeHtmlEntities" in response.text
    assert 'container.innerHTML = String(text || "")' not in response.text
    assert "announce(?:ment)?\\s+type" in response.text
    assert "暂无可用摘要。" in response.text
    assert "TOC\\s+Graphic" in response.text
    assert "paperCanonicalKey" in response.text
    assert "paperReadingKey" in response.text
    assert "mergeDailyPaper" in response.text
    assert "_canonical_key" in response.text
    assert "_daily_sources" in response.text
    assert "多来源" in response.text
    assert "出现来源" in response.text
    assert "paperlite.read.v1" in response.text
    assert "paperlite.favorite.v1" in response.text
    assert "paperlite.hideRead.v1" in response.text
    assert 'id="hideReadBtn"' in response.text
    assert 'id="dailyViewBtn"' in response.text
    assert 'id="favoritesViewBtn"' in response.text
    assert "toggleRead" in response.text
    assert "toggleFavorite" in response.text
    assert "toggleHideRead" in response.text
    assert "is-read" in response.text
    assert "is-favorite" in response.text
    assert "隐藏已读" in response.text
    assert "全部缓存" in response.text
    assert "收藏夹" in response.text
    assert "SQLite 个人库 / 收藏" in response.text
    assert "收藏夹还是空的" in response.text
    assert "已收藏" in response.text
    assert 'data-action="translate"' not in response.text
    assert 'id="chainStatus"' in response.text
    assert "/zotero/export?format=ris" in response.text
    assert "发送到 Zotero 失败" in response.text
    assert "检查 Zotero 状态失败" in response.text
    assert "是否改为导出 RIS 文件" in response.text
    assert "window.confirm(message)" in response.text
    assert "已取消 RIS 导出" in response.text
    assert "buildDailyExportUrl" in response.text
    assert "exportCurrentResults" in response.text
    assert 'data-export-format="ris"' in response.text
    assert 'data-export-format="bibtex"' in response.text
    assert 'data-export-format="markdown"' in response.text
    assert 'data-export-format="json"' in response.text
    assert 'data-export-format="jsonl"' in response.text
    assert 'data-export-format="rss"' in response.text
    assert "/daily/enrich?source=" in response.text
    assert "enrichments: new Map()" in response.text
    assert "renderEnrichmentStatus" in response.text
    assert "renderEnrichmentEvidence" in response.text
    assert "renderDetailMetadata" in response.text
    assert "source_records" in response.text
    assert "补全资料" in response.text
    assert "补全信息" in response.text
    assert "metadata-chip" in response.text
    assert "期刊/会议" in response.text
    assert "出版社" in response.text
    assert "主题" in response.text
    assert "Crossref" in response.text
    assert "PubMed" in response.text
    assert "Europe PMC" in response.text
    assert "enrich_warnings" in response.text
    assert "补全中" in response.text
    assert "正在查 OpenAlex / Crossref / PubMed / Europe PMC" in response.text
    assert "新增/更新" in response.text
    assert "已查询，暂无新增字段" in response.text
    assert "sourceAvailability" in response.text
    assert "sourceCrawlCompatible" in response.text
    assert "incompatibleSelectedSources" in response.text
    assert "已清除 ${removed} 个与该学科不匹配的来源" in response.text
    assert "已选来源与学科不匹配或不可抓取" in response.text
    assert "sourceSearch\").value = \"\"" in response.text
    assert "payload.detail || payload.error || payload.message" in response.text
    assert "source-status-badge" in response.text
    assert "health_status" in response.text
    assert "quality_status" in response.text
    assert "不可抓取" in response.text
    assert "暂不可用" in response.text
    assert "1 选择范围" in response.text
    assert "2 抓取/缓存" in response.text
    assert "3 复核阅读" in response.text
    assert "4 批量补全/翻译" in response.text
    assert "5 导出/Zotero" in response.text
    assert 'id="selectionText"' in response.text
    assert 'id="batchReadBtn"' in response.text
    assert 'id="batchFavoriteBtn"' in response.text
    assert 'id="batchHideBtn"' in response.text
    assert 'id="batchTranslateBtn"' in response.text
    assert 'id="batchEnrichBtn"' in response.text
    assert 'id="batchZoteroBtn"' in response.text
    assert 'class="paper-select"' in response.text
    assert "/library/state" in response.text
    assert "/library/action" in response.text
    assert "/library/items?state=favorite" in response.text
    assert "/library/views" in response.text
    assert "syncLibraryState" in response.text
    assert "loadFavoriteShelf" in response.text
    assert "applyLibraryActionClient" in response.text
    assert "Library API 不可用，使用本地状态" in response.text
    assert "paperlite.hidden.v1" in response.text
    assert "保存视图" in response.text
    assert "加载视图" in response.text
    assert "currentViewFilters" in response.text
    assert "loadSavedViews" in response.text


def test_daily_frontend_reads_cache_by_explicit_date_range():
    client = TestClient(api.create_app())

    response = client.get("/daily")

    assert response.status_code == 200
    assert "function dateRangeDayCount" in response.text
    assert "function daysBetween" not in response.text
    assert "dates.length < 31" not in response.text
    assert "Promise.all(days.map" not in response.text
    assert 'params.set("date_from", dateFrom);' in response.text
    assert 'params.set("date_to", dateTo);' in response.text
    assert 'fetchJson(`/daily/cache?${cacheParams($("dateFrom").value, $("dateTo").value, limitPerSource).toString()}`)' in response.text


def test_ops_page_exposes_runtime_panel_without_auto_crawl_or_health_check():
    client = TestClient(api.create_app())

    response = client.get("/ops")

    assert response.status_code == 200
    assert "PaperLite 运行面板" in response.text
    assert "抓取任务" in response.text
    assert "定时任务" in response.text
    assert "运行摘要" in response.text
    assert "DB、缓存、最近错误、下一次计划任务" in response.text
    assert "来源覆盖" in response.text
    assert "来源健康" in response.text
    assert "来源内容体检" in response.text
    assert "不会自动跑，手动触发；每源只抽样少量元数据" in response.text
    assert "/ops/status?limit=20" in response.text
    assert "/ops/doctor" in response.text
    assert "/ops/health/check" in response.text
    assert "/ops/source-audit" in response.text
    assert "/ops/source-audit/check" in response.text
    assert "/.well-known/paperlite.json" in response.text
    assert "/catalog/coverage" in response.text
    assert "renderRuntimeSummary" in response.text
    assert "cache_summary" in response.text
    assert "run_summary" in response.text
    assert "schedule_summary" in response.text
    assert "source_audit_summary" in response.text
    assert "renderSourceAudit" in response.text
    assert "checkSourceAudit" in response.text
    assert 'id="auditCheckBtn"' in response.text
    assert 'id="auditNextBtn"' in response.text
    assert 'id="auditIssuesBtn"' in response.text
    assert "recent_errors" in response.text
    assert "failed_sources" in response.text
    assert "health_age" in response.text
    assert "renderCoverage" in response.text
    assert "addEventListener(\"click\", checkHealth)" in response.text
    assert "addEventListener(\"click\", () => checkSourceAudit())" in response.text
    assert 'method: "POST"' in response.text
    assert 'fetchJson("/daily/crawl", {' not in response.text
    assert "checkSourceAudit().catch" not in response.text


def test_daily_live_machine_formats_are_removed():
    client = TestClient(api.create_app())

    json_response = client.get(
        "/daily",
        params={"format": "json", "source": "arxiv", "date": "2024-01-02", "limit_per_source": "2"},
    )
    rss_response = client.get("/daily", params={"format": "rss", "source": "arxiv", "date": "2024-01-02"})

    assert json_response.status_code == 410
    assert rss_response.status_code == 410
    assert "/daily/cache?format=json" in json_response.json()["detail"]
    assert "/daily/export?format=rss" in json_response.json()["detail"]
    assert "/daily/cache?format=json" in rss_response.json()["detail"]
    assert "/daily/export?format=rss" in rss_response.json()["detail"]


def test_sources_returns_html_matrix_for_browser_accept():
    client = TestClient(api.create_app())

    response = client.get("/sources", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PaperLite 来源说明" in response.text
    assert "外链优先" in response.text
    assert "可搜索" in response.text
    assert "最近快讯" in response.text
    assert "不下载、不缓存、不代理全文或 PDF" in response.text
    assert "获取方式" in response.text
    assert 'href="/endpoints"' in response.text
    assert 'href="/categories"' in response.text
    assert "分类映射" in response.text
    assert "源目录体检" not in response.text
    assert "核心源" in response.text
    assert "治理状态" in response.text


def test_endpoints_returns_html_and_json():
    client = TestClient(api.create_app())

    html = client.get("/endpoints", headers={"accept": "text/html"})
    json_response = client.get("/endpoints?format=json", headers={"accept": "text/html"})

    assert html.status_code == 200
    assert "PaperLite 获取方式" in html.text
    assert "endpoint 是获取路径" in html.text
    assert 'href="/endpoints?mode=rss"' in html.text
    assert "当前筛选：全部" in html.text
    assert "暂不可用" in html.text
    assert json_response.status_code == 200
    payload = json_response.json()
    assert len(payload["endpoints"]) >= 700
    assert any(item["key"] == "arxiv" and item["mode"] == "api" for item in payload["endpoints"])


def test_endpoints_can_filter_by_mode():
    client = TestClient(api.create_app())

    rss = client.get("/endpoints?format=json&mode=rss")
    manual = client.get("/endpoints?format=json&mode=manual")
    html = client.get("/endpoints?mode=rss", headers={"accept": "text/html"})
    bad = client.get("/endpoints?mode=bad")

    assert rss.status_code == 200
    assert rss.json()["endpoints"]
    assert all(item["mode"] == "rss" for item in rss.json()["endpoints"])
    assert manual.status_code == 200
    assert manual.json()["endpoints"]
    assert all(item["mode"] == "manual" for item in manual.json()["endpoints"])
    assert html.status_code == 200
    assert "当前筛选：RSS" in html.text
    assert 'class="active" href="/endpoints?mode=rss">RSS' in html.text
    assert 'href="/endpoints?mode=rss&amp;format=json"' in html.text
    assert bad.status_code == 400
    assert "unknown endpoint mode" in bad.json()["detail"]


def test_catalog_summary_and_source_filters_are_exposed():
    client = TestClient(api.create_app())

    summary = client.get("/catalog/summary?format=json")
    html = client.get("/catalog/summary", headers={"accept": "text/html"})
    coverage = client.get("/catalog/coverage?format=json")
    coverage_md = client.get("/catalog/coverage?format=markdown")
    filtered = client.get("/sources?format=json&discipline=Medicine&core=true")
    area_filtered = client.get("/sources?format=json&area=life_health")

    assert summary.status_code == 200
    payload = summary.json()
    assert payload["source_count"] >= 800
    assert payload["endpoint_mode_counts"]["rss"] >= 600
    assert payload["missing_discipline_count"] >= 0
    assert html.status_code == 200
    assert "PaperLite 源目录体检" in html.text
    assert coverage.status_code == 200
    assert coverage.json()["totals"]["source_count"] >= 800
    assert coverage.json()["totals"]["runnable_source_count"] > 0
    assert coverage_md.status_code == 200
    assert "PaperLite 来源覆盖" in coverage_md.text
    assert filtered.status_code == 200
    sources = filtered.json()["sources"]
    assert sources
    assert all("Medicine" in item["canonical_disciplines"] for item in sources)
    assert all(item["core"] is True for item in sources)
    assert all("quality_status" in item and "health_status" in item for item in sources)
    assert area_filtered.status_code == 200
    area_sources = area_filtered.json()["sources"]
    assert area_sources
    assert all("life_health" in item["area_keys"] for item in area_sources)


def test_categories_page_and_json_expose_stable_taxonomy():
    client = TestClient(api.create_app())

    json_response = client.get("/categories?format=json")
    html_response = client.get("/categories", headers={"accept": "text/html"})
    markdown_response = client.get("/categories?format=markdown")

    assert json_response.status_code == 200
    payload = json_response.json()
    assert "primary_discipline_key" in payload["maintenance_fields"]
    assert "category_keys" in payload["maintenance_fields"]
    assert "category_key" in payload["maintenance_fields"]
    assert any(item["key"] == "medicine" for item in payload["disciplines"])
    assert any(item["key"] == "journal" for item in payload["source_kinds"])
    assert any(item["key"].endswith(".journal") for item in payload["categories"])
    assert html_response.status_code == 200
    assert "PaperLite 分类映射" in html_response.text
    assert "分类不是推荐" in html_response.text
    assert "primary_discipline_key" in html_response.text
    assert markdown_response.status_code == 200
    assert "PaperLite 分类映射" in markdown_response.text


def test_endpoints_can_filter_by_status():
    client = TestClient(api.create_app())

    response = client.get("/endpoints?format=json&status=temporarily_unavailable")
    html = client.get("/endpoints?status=temporarily_unavailable", headers={"accept": "text/html"})

    assert response.status_code == 200
    endpoints = response.json()["endpoints"]
    assert endpoints
    assert all(item["status"] == "temporarily_unavailable" for item in endpoints)
    assert html.status_code == 200
    assert "temporarily_unavailable" in html.text


def test_daily_html_ignores_old_live_daily_params():
    client = TestClient(api.create_app())

    response = client.get(
        "/daily",
        params={"format": "html", "endpoint": "arxiv_cs_lg", "source": "nature", "profile": "ai"},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PaperLite" in response.text


def test_sources_format_json_keeps_machine_contract():
    client = TestClient(api.create_app())

    response = client.get("/sources?format=json", headers={"accept": "text/html"})

    assert response.status_code == 200
    payload = response.json()
    arxiv = next(item for item in payload["sources"] if item["name"] == "arxiv")
    assert arxiv["search_mode"] == "native_api"
    assert arxiv["full_text_policy"] == "external_only"
    assert arxiv["endpoint_count"] == 1
    assert arxiv["primary_endpoint"] == "arxiv"
    assert arxiv["catalog_kind"] == "preprint"
    assert "quality_status" in arxiv
    assert "canonical_disciplines" in arxiv
    assert arxiv["primary_discipline_key"] == "multidisciplinary"
    assert arxiv["source_kind_key"] == "preprint"
    assert arxiv["category_keys"] == ["multidisciplinary.preprint"]
    assert arxiv["category_key"] == "multidisciplinary.preprint"
    nature = next(item for item in payload["sources"] if item["name"] == "nature")
    assert nature["multidisciplinary_supplement"] is True
    comms_chem = next(item for item in payload["sources"] if item["name"] == "nature_commschem")
    assert comms_chem["primary_discipline_key"] == "chemistry"
    assert comms_chem["multidisciplinary_supplement"] is False
    assert "general" in arxiv["area_keys"]


def test_removed_old_papers_routes_return_404():
    client = TestClient(api.create_app())

    latest = client.get("/papers?source=arxiv&limit=1&format=json", headers={"accept": "text/html"})
    search = client.get("/papers/search?q=diffusion&source=arxiv", headers={"accept": "text/html"})
    detail = client.get("/papers/arxiv:1")
    rss = client.get("/export/rss")
    old_enrich = client.post("/papers/enrich?source=openalex", json=make_paper().to_dict())

    assert latest.status_code == 404
    assert search.status_code == 404
    assert detail.status_code == 404
    assert rss.status_code == 404
    assert old_enrich.status_code == 404


def test_zotero_status_does_not_leak_key(monkeypatch):
    monkeypatch.setattr(api, "zotero_status", lambda: {"configured": True, "library_type": "user", "library_id": "1"})
    client = TestClient(api.create_app())

    response = client.get("/zotero/status")

    assert response.status_code == 200
    assert response.json() == {"configured": True, "library_type": "user", "library_id": "1"}
    assert "API_KEY" not in response.text


def test_zotero_items_accepts_paper_dicts(monkeypatch):
    captured = {}

    def fake_create_zotero_items(papers):
        captured["papers"] = papers
        return {"configured": True, "submitted": len(papers), "created": [{"paper_id": papers[0].id}], "failed": []}

    monkeypatch.setattr(api, "create_zotero_items", fake_create_zotero_items)
    client = TestClient(api.create_app())

    response = client.post("/zotero/items", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 200
    assert response.json()["submitted"] == 1
    assert captured["papers"][0].id == "arxiv:1"


def test_zotero_items_returns_503_when_unconfigured(monkeypatch):
    def fake_create_zotero_items(_papers):
        raise api.ZoteroNotConfiguredError("missing zotero config")

    monkeypatch.setattr(api, "create_zotero_items", fake_create_zotero_items)
    client = TestClient(api.create_app())

    response = client.post("/zotero/items", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 503
    assert response.json()["detail"] == "missing zotero config"


def test_zotero_items_returns_502_when_zotero_request_fails(monkeypatch):
    def fake_create_zotero_items(_papers):
        raise api.ZoteroRequestError("Zotero API request timed out")

    monkeypatch.setattr(api, "create_zotero_items", fake_create_zotero_items)
    client = TestClient(api.create_app())

    response = client.post("/zotero/items", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 502
    assert response.json()["detail"] == "Zotero API request timed out"


def test_zotero_export_returns_ris_without_api_key():
    client = TestClient(api.create_app())

    response = client.post("/zotero/export?format=ris", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 200
    assert "application/x-research-info-systems" in response.headers["content-type"]
    assert 'filename="paperlite-zotero.ris"' in response.headers["content-disposition"]
    assert "TY  - RPRT" in response.text
    assert "N1  - External PDF URL: https://example.com/arxiv:1.pdf" in response.text
    assert "ZOTERO_API_KEY" not in response.text


def test_zotero_export_returns_bibtex_without_api_key():
    client = TestClient(api.create_app())

    response = client.post("/zotero/export?format=bibtex", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 200
    assert "application/x-bibtex" in response.headers["content-type"]
    assert 'filename="paperlite-zotero.bib"' in response.headers["content-disposition"]
    assert "@misc{arxiv_1," in response.text
    assert "External PDF URL: https://example.com/arxiv:1.pdf" in response.text


def test_zotero_export_rejects_unknown_format():
    client = TestClient(api.create_app())

    response = client.post("/zotero/export?format=docx", json={"items": [make_paper().to_dict()]})

    assert response.status_code == 400
    assert response.json()["detail"] == "format must be ris or bibtex"


def test_agent_translate_endpoint(monkeypatch):
    calls = []

    def fake_translate(**kwargs):
        calls.append(kwargs)
        return {
            "paper": kwargs["paper"],
            "target_language": kwargs["target_language"],
            "style": kwargs["style"],
            "translation_profile": kwargs["translation_profile"],
            "translation": "translated",
            "configured": True,
            "model": "mock",
            "warnings": [],
        }

    monkeypatch.setattr(
        api,
        "translate_paper",
        fake_translate,
    )
    client = TestClient(api.create_app())

    response = client.post(
        "/agent/translate",
        json={
            "paper": make_paper().to_dict(),
            "target_language": "zh-CN",
            "translation_profile": "research_card_cn",
        },
    )

    assert response.status_code == 200
    assert response.json()["target_language"] == "zh-CN"
    assert response.json()["translation_profile"] == "research_card_cn"
    assert response.json()["translation"] == "translated"
    assert calls[0]["style"] is None
    assert calls[0]["translation_profile"] == "research_card_cn"


def test_agent_translation_profiles_endpoint():
    client = TestClient(api.create_app())

    response = client.get("/agent/translation-profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 2
    keys = {profile["key"] for profile in payload["profiles"]}
    assert {"research_card_cn", "detail_cn"} <= keys


def test_daily_enrich_endpoint(monkeypatch):
    calls = []

    def fake_enrich_paper(paper, source):
        calls.append((paper.id, source))
        return paper.model_copy(update={"doi": "10.1234/enriched"})

    monkeypatch.setattr(api, "enrich_paper", fake_enrich_paper)
    client = TestClient(api.create_app())

    response = client.post("/daily/enrich?source=openalex,crossref", json=make_paper().to_dict())

    assert response.status_code == 200
    assert response.json()["doi"] == "10.1234/enriched"
    assert calls == [("arxiv:1", "openalex,crossref")]


def test_agent_filter_endpoint(monkeypatch):
    profile_calls = []
    query_calls = []

    def fake_profile(**kwargs):
        profile_calls.append(kwargs)
        return {"profile": {"summary": "长期提示词：Prefer RAG"}}

    def fake_record_query(**kwargs):
        query_calls.append(kwargs)
        return {"text": kwargs["text"], "source": kwargs["source"], "use_count": 1}

    monkeypatch.setattr(
        api,
        "filter_paper",
        lambda **kwargs: {
            "paper": kwargs["paper"],
            "query": kwargs["query"],
            "profile_used": bool(kwargs.get("preference_profile")) and kwargs.get("use_profile") is not False,
            "group": "recommend",
            "importance": 91,
            "include": True,
            "reason": "highly relevant",
            "confidence": 0.9,
            "configured": True,
            "model": "mock",
            "warnings": [],
        },
    )
    monkeypatch.setattr(api, "get_relevant_preference_profile", fake_profile)
    monkeypatch.setattr(api, "record_preference_query", fake_record_query)
    client = TestClient(api.create_app())

    response = client.post("/agent/filter", json={"paper": make_paper().to_dict(), "query": "useful"})
    defaulted = client.post("/agent/filter", json={"paper": make_paper().to_dict()})
    unprofiled = client.post("/agent/filter", json={"paper": make_paper().to_dict(), "query": "useful", "use_profile": False})

    assert response.status_code == 200
    assert response.json()["query"] == "useful"
    assert response.json()["profile_used"] is True
    assert response.json()["group"] == "recommend"
    assert response.json()["importance"] == 91
    assert defaulted.status_code == 200
    assert defaulted.json()["query"] == DEFAULT_AI_FILTER_QUERY
    assert unprofiled.status_code == 200
    assert unprofiled.json()["profile_used"] is False
    assert len(profile_calls) == 2
    assert profile_calls[0]["query"] == "useful"
    assert profile_calls[0]["paper"]["id"] == "arxiv:1"
    assert profile_calls[1]["query"] == DEFAULT_AI_FILTER_QUERY
    assert query_calls == [{"text": "useful", "source": "agent_filter"}]
