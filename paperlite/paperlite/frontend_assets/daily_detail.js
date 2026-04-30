    function renderEnrichmentStatus(status) {
      const warnings = status.warnings || [];
      const warningHtml = warnings.length
        ? `<div class="enrichment-warnings">${escapeHtml(warnings.join("；"))}</div>`
        : "";
      const evidenceHtml = renderEnrichmentEvidence(status.evidence || {});
      return `
        <div class="enrichment ${escapeHtml(status.status || "")}">
          <strong>${escapeHtml(status.label || "补全")}</strong> ${escapeHtml(status.message || "")}
          ${evidenceHtml}
          ${warningHtml}
        </div>
      `;
    }

    function evidenceSourceLabel(value) {
      const labels = {
        openalex: "OpenAlex",
        crossref: "Crossref",
        pubmed: "PubMed",
        europepmc: "Europe PMC",
        europe_pmc: "Europe PMC",
      };
      const key = String(value || "").toLowerCase().replace(/[\s-]+/g, "_");
      return labels[key] || value || "metadata";
    }

    function compactMetadataList(values, limit = 6) {
      const seen = new Set();
      const compacted = [];
      for (const value of values || []) {
        const text = String(value || "").trim();
        const key = text.toLowerCase();
        if (!text || seen.has(key)) continue;
        seen.add(key);
        compacted.push(text);
      }
      return compacted.slice(0, limit);
    }

    function metadataChip(label, value) {
      if (!fieldPresent(value)) return "";
      const text = Array.isArray(value) ? compactMetadataList(value).join(" / ") : String(value);
      return text ? `<span class="metadata-chip"><strong>${escapeHtml(label)}</strong>${escapeHtml(text)}</span>` : "";
    }

    function renderDetailMetadata(paper) {
      const topics = compactMetadataList([...(paper.concepts || []), ...(paper.categories || [])], 8);
      const chips = [
        metadataChip("期刊/会议", paper.venue || paper.journal),
        metadataChip("出版社", paper.publisher),
        metadataChip("引用", paper.citation_count != null ? paper.citation_count : ""),
        metadataChip("主题", topics),
        metadataChip("PubMed", paper.pmid ? `PMID ${paper.pmid}` : ""),
        metadataChip("PMC", paper.pmcid ? `PMCID ${paper.pmcid}` : ""),
      ].filter(Boolean).join("");
      if (!chips) return "";
      return `
        <div class="detail-facts">
          <div class="detail-facts-title">补全信息</div>
          <div class="metadata-chips">${chips}</div>
        </div>
      `;
    }

    function compactEvidenceRecord(record) {
      const pieces = [
        record.id,
        record.doi ? `DOI ${record.doi}` : "",
        record.pmid ? `PMID ${record.pmid}` : "",
        record.pmcid ? `PMCID ${record.pmcid}` : "",
        record.cited_by_count != null ? `引用 ${record.cited_by_count}` : "",
        record.type,
        record.publisher,
      ].filter(Boolean);
      return pieces.slice(0, 4).join(" · ");
    }

    function renderEnrichmentEvidence(evidence) {
      const records = Array.isArray(evidence.source_records) ? evidence.source_records : [];
      const identifiers = evidence.identifiers || {};
      const metadata = evidence.metadata || {};
      const topics = compactMetadataList([...(metadata.concepts || []), ...(metadata.categories || [])], 8);
      const authors = compactMetadataList(metadata.authors || [], 6);
      const idRows = [
        identifiers.doi ? `<div class="evidence-row"><span class="evidence-label">DOI</span> ${escapeHtml(identifiers.doi)}</div>` : "",
        identifiers.openalex_id ? `<div class="evidence-row"><span class="evidence-label">OpenAlex</span> ${externalLink(identifiers.openalex_id, "Work") || escapeHtml(identifiers.openalex_id)}</div>` : "",
        identifiers.pmid ? `<div class="evidence-row"><span class="evidence-label">PubMed</span> PMID ${escapeHtml(identifiers.pmid)}</div>` : "",
        identifiers.pmcid ? `<div class="evidence-row"><span class="evidence-label">Europe PMC</span> PMCID ${escapeHtml(identifiers.pmcid)}</div>` : "",
        identifiers.pdf_url ? `<div class="evidence-row"><span class="evidence-label">PDF</span> ${externalLink(identifiers.pdf_url, "源站 PDF") || escapeHtml(identifiers.pdf_url)}</div>` : "",
        identifiers.citation_count != null ? `<div class="evidence-row"><span class="evidence-label">引用</span> ${escapeHtml(identifiers.citation_count)}</div>` : "",
      ].filter(Boolean).join("");
      const metaRows = [
        metadata.venue || metadata.journal ? `<div class="evidence-row"><span class="evidence-label">期刊/会议</span> ${escapeHtml(metadata.venue || metadata.journal)}</div>` : "",
        metadata.publisher ? `<div class="evidence-row"><span class="evidence-label">出版社</span> ${escapeHtml(metadata.publisher)}</div>` : "",
        authors.length ? `<div class="evidence-row"><span class="evidence-label">作者</span> ${escapeHtml(authors.join(" / "))}</div>` : "",
        topics.length ? `<div class="evidence-row"><span class="evidence-label">主题</span> ${escapeHtml(topics.join(" / "))}</div>` : "",
      ].filter(Boolean).join("");
      const recordRows = records.map((record) => {
        const source = evidenceSourceLabel(record.source || record.provider);
        const detail = compactEvidenceRecord(record);
        return `<div class="evidence-row"><span class="evidence-label">${escapeHtml(source)}</span>${detail ? ` ${escapeHtml(detail)}` : ""}</div>`;
      }).join("");
      if (!idRows && !metaRows && !recordRows) return "";
      return `
        <div class="evidence">
          <div class="evidence-title">补全资料</div>
          ${idRows}
          ${metaRows}
          ${recordRows}
        </div>
      `;
    }

    function fieldPresent(value) {
      return value !== undefined && value !== null && value !== "" && !(Array.isArray(value) && value.length === 0);
    }

    function enrichmentChanges(before, after) {
      const changes = [];
      const checks = [
        ["doi", "DOI"],
        ["abstract", "摘要"],
        ["openalex_id", "OpenAlex"],
        ["pmid", "PubMed"],
        ["pmcid", "PMC"],
        ["pdf_url", "PDF"],
        ["citation_count", "引用"],
        ["journal", "期刊"],
        ["venue", "期刊"],
        ["publisher", "出版社"],
      ];
      for (const [field, label] of checks) {
        if (!fieldPresent(before[field]) && fieldPresent(after[field]) && !changes.includes(label)) changes.push(label);
      }
      if ((after.authors || []).length > (before.authors || []).length) changes.push("作者");
      if ((after.categories || []).length > (before.categories || []).length || (after.concepts || []).length > (before.concepts || []).length) changes.push("分类");
      if ((after.source_records || []).length > (before.source_records || []).length) changes.push("来源记录");
      return changes;
    }

    function enrichmentEvidence(paper) {
      const records = Array.isArray(paper.source_records) ? paper.source_records : [];
      return {
        identifiers: {
          doi: paper.doi || "",
          openalex_id: paper.openalex_id || "",
          pmid: paper.pmid || "",
          pmcid: paper.pmcid || "",
          pdf_url: paper.pdf_url || "",
          citation_count: paper.citation_count,
        },
        metadata: {
          venue: paper.venue || "",
          journal: paper.journal || "",
          publisher: paper.publisher || "",
          authors: paper.authors || [],
          concepts: paper.concepts || [],
          categories: paper.categories || [],
        },
        source_records: records,
      };
    }

    function mergeClientPaper(before, after) {
      return {
        ...before,
        ...after,
        _daily_date: before._daily_date,
        _daily_source: before._daily_source,
        _daily_source_display: before._daily_source_display,
        _cache_date: before._cache_date,
        _canonical_key: before._canonical_key || after._canonical_key || paperCanonicalKey(before),
        _daily_sources: before._daily_sources || after._daily_sources,
        _daily_source_records: before._daily_source_records || after._daily_source_records,
      };
    }

    function replacePaperEverywhere(id, enriched) {
      state.currentItems = state.currentItems.map((item) => item.id === id ? mergeClientPaper(item, enriched) : item);
      state.allItems = state.allItems.map((item) => item.id === id ? mergeClientPaper(item, enriched) : item);
    }
    function decodeHtmlEntities(text) {
      const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
      return String(text || "").replace(/&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]+);/gi, (match, entity) => {
        const key = entity.toLowerCase();
        if (key in named) return named[key];
        if (key.startsWith("#x")) {
          const value = Number.parseInt(key.slice(2), 16);
          return Number.isFinite(value) ? String.fromCodePoint(value) : match;
        }
        if (key.startsWith("#")) {
          const value = Number.parseInt(key.slice(1), 10);
          return Number.isFinite(value) ? String.fromCodePoint(value) : match;
        }
        return match;
      });
    }
    function htmlToPlainText(text) {
      return decodeHtmlEntities(String(text || "")
        .replace(/<!--[\s\S]*?-->/g, " ")
        .replace(/<script\b[\s\S]*?<\/script\s*>/gi, " ")
        .replace(/<style\b[\s\S]*?<\/style\s*>/gi, " ")
        .replace(/<\/?(?:p|div|br|li|tr|td|th|h[1-6]|section|article|blockquote)\b[^>]*>/gi, " ")
        .replace(/<[^>]+>/g, " "));
    }
    function cleanAbstractText(text) {
      return htmlToPlainText(text)
        .replace(/^\s*arxiv\s*:\s*\d{4}\.\d{4,5}(?:v\d+)?(?:\s*\[[^\]]+\])?\s*/i, " ")
        .replace(/^\s*announce(?:ment)?\s+type\s*:?\s*[A-Za-z_-]{1,30}\s*/i, " ")
        .replace(/^\s*(?:abstract|summary)\s*:\s*/i, " ")
        .replace(/\bTOC\s+Graphic\b/ig, " ")
        .replace(/\bDOI\s*:\s*\S+/ig, " ")
        .replace(/\s+/g, " ")
        .trim();
    }
    function usableAbstractText(text) {
      const cleaned = cleanAbstractText(text);
      const englishWords = cleaned.match(/[A-Za-z][A-Za-z-]+/g) || [];
      const cjkChars = cleaned.match(/[\u4e00-\u9fff]/g) || [];
      if (cleaned.length < 80 && cjkChars.length < 40) return "";
      if (englishWords.length < 12 && cjkChars.length < 40) return "";
      return cleaned;
    }
    function relatedPaperLinks(paper) {
      const links = [];
      if (paper.url) links.push(externalLink(paper.url, "外部页面"));
      if (paper.doi) links.push(externalLink(`https://doi.org/${paper.doi}`, "DOI"));
      if (paper.openalex_id) links.push(externalLink(paper.openalex_id, "OpenAlex"));
      return links.filter(Boolean).join(" · ");
    }
    function renderRelatedPapers(paper) {
      const stateItem = state.relatedPapers.get(paper.id);
      if (!stateItem || stateItem.status === "loading") {
        return `
          <div class="related-papers loading">
            <div class="related-title">相关论文</div>
            <div class="related-message">正在用本地缓存 metadata 计算相似论文...</div>
          </div>
        `;
      }
      if (stateItem.status === "error") {
        return `
          <div class="related-papers error">
            <div class="related-title">相关论文</div>
            <div class="related-message">加载失败：${escapeHtml(stateItem.error || "unknown error")}</div>
          </div>
        `;
      }
      const payload = stateItem.payload || {};
      const warnings = (payload.warnings || []).filter(Boolean);
      const related = Array.isArray(payload.related) ? payload.related : [];
      const warningHtml = warnings.length
        ? `<div class="related-warnings">${escapeHtml(warnings.join(" / "))}</div>`
        : "";
      const rows = related.map((item) => {
        const relatedPaper = item.paper || {};
        const score = Number.isFinite(Number(item.score)) ? Number(item.score).toFixed(3) : "";
        const links = relatedPaperLinks(relatedPaper);
        return `
          <div class="related-row">
            <div class="related-row-title">${escapeHtml(relatedPaper.title || "Untitled")}</div>
            <div class="related-row-meta">
              ${escapeHtml([relatedPaper.source, relatedPaper.venue || relatedPaper.journal, relatedPaper.published_at, score ? `相似 ${score}` : ""].filter(Boolean).join(" · "))}
            </div>
            ${links ? `<div class="related-row-links">${links}</div>` : ""}
          </div>
        `;
      }).join("");
      return `
        <div class="related-papers">
          <div class="related-title">相关论文</div>
          ${warningHtml}
          ${rows || `<div class="related-message">当前筛选范围内暂无可推荐的相似论文。</div>`}
        </div>
      `;
    }
    function renderDetail(paper) {
      const authors = (paper.authors || []).slice(0, 12).join(", ");
      const abstract = usableAbstractText(paper.abstract) || "暂无可用摘要。";
      const identifier = paperIdentifierLabel(paper);
      const hasTranslation = state.detailTranslations.has(paper.id);
      const translateBusy = state.translationInFlight || state.detailTranslationInFlightIds.has(paper.id);
      const translateLabel = translateBusy ? "直译中" : (hasTranslation ? "已直译" : "翻译详情");
      const translateDisabled = translateBusy || hasTranslation ? "disabled" : "";
      const links = [
        externalLink(paper.url, "外部页面"),
        externalLink(paper.pdf_url, "PDF"),
        externalLink(paper.openalex_id, "OpenAlex"),
      ].filter(Boolean).join("");
      const dailySources = Array.isArray(paper._daily_sources) ? paper._daily_sources : [];
      const sourceEvidence = dailySources.length > 1
        ? `<p class="detail-meta">出现来源：${escapeHtml(dailySources.join(" / "))}</p>`
        : "";
      const action = `<button class="detail-action" data-action="translate-detail" title="翻译这一条详情；已有翻译不会重复请求 LLM" type="button" ${translateDisabled}>${translateLabel}</button>`;
      return `
        <div class="detail">
          <p class="detail-summary">${escapeHtml(abstract)}</p>
          <p class="detail-meta">${escapeHtml([authors, identifier, paper.citation_count != null ? `引用 ${paper.citation_count}` : ""].filter(Boolean).join(" · "))}</p>
          ${renderDetailMetadata(paper)}
          ${sourceEvidence}
          ${renderRelatedPapers(paper)}
          <div class="detail-tools">
            <div class="detail-links">${links}</div>
            ${action}
          </div>
        </div>
      `;
    }
    function renderTranslation(payload) {
      const data = typeof payload === "string" ? { translation: payload } : (payload || {});
      const brief = data.brief || {};
      const title = data.title_zh || data.card_headline || brief.card_headline || "";
      const flash = data.cn_flash_180 || brief.cn_flash_180 || "";
      const bullets = Array.isArray(data.card_bullets) ? data.card_bullets : (Array.isArray(brief.card_bullets) ? brief.card_bullets : []);
      const tags = Array.isArray(data.card_tags) ? data.card_tags : (Array.isArray(brief.card_tags) ? brief.card_tags : []);
      const fallbackParts = !flash && data.translation
        ? String(data.translation).split(/\n+/).map((line) => line.trim()).filter(Boolean)
        : [];
      const titleHtml = title ? `<p class="translation-title">${escapeHtml(title)}</p>` : "";
      const flashHtml = flash ? `<p>${escapeHtml(flash)}</p>` : "";
      const missingAbstractHtml = data.abstract_missing && !flash ? `<p>原始记录无摘要，仅跳过摘要 brief。</p>` : "";
      const fallbackHtml = fallbackParts.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
      const bulletHtml = bullets.length
        ? `<div class="translation-bullets">${bullets.map((item) => `
            <div class="translation-bullet">
              <span class="translation-bullet-label">${escapeHtml(item.label || "")}</span>
              <span>${escapeHtml(item.text || "")}</span>
            </div>
          `).join("")}</div>`
        : "";
      const tagHtml = tags.length
        ? `<div class="translation-tags">${tags.map((tag) => `<span class="translation-tag">${escapeHtml(tag)}</span>`).join("")}</div>`
        : "";
      const body = titleHtml || flashHtml || bulletHtml || tagHtml || fallbackHtml
        ? `${titleHtml}${flashHtml}${missingAbstractHtml}${bulletHtml}${tagHtml}${fallbackHtml}`
        : (missingAbstractHtml || "<p>暂无翻译。</p>");
      return `
        <div class="translation">
          <span class="translation-label">Brief 翻译</span>
          ${body}
        </div>
      `;
    }
    function renderDetailTranslation(payload) {
      const data = payload || {};
      const detail = data.detail_translation || data.translation || "";
      const body = data.detail_skipped
        ? "<p>暂无可翻译详情。</p>"
        : (detail ? `<p>${escapeHtml(detail)}</p>` : "<p>暂无详情直译。</p>");
      return `
        <div class="translation">
          <span class="translation-label">详情直译</span>
          ${body}
        </div>
      `;
    }
