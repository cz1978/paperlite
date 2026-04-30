    const PAGE_SIZE = 30;
    const ENRICHERS = "openalex,crossref,pubmed,europepmc";
    const TRANSLATE_BATCH_DELAY_MS = 1000;
    const TRANSLATE_RETRY_BASE_MS = 1500;
    const TRANSLATE_MAX_RETRIES = 3;
    const AI_FILTER_BATCH_DELAY_MS = 1000;
    const AI_FILTER_RETRY_BASE_MS = 1500;
    const AI_FILTER_MAX_RETRIES = 3;
    const AI_FILTER_MAX_SCAN = 120;
    const DEFAULT_AI_FILTER_LABEL = "默认学术价值筛选";
    const READ_STORAGE_KEY = "paperlite.read.v1";
    const FAVORITE_STORAGE_KEY = "paperlite.favorite.v1";
    const HIDE_READ_STORAGE_KEY = "paperlite.hideRead.v1";
    const HIDDEN_STORAGE_KEY = "paperlite.hidden.v1";
    const state = {
      sources: [],
      selectedSources: new Set(),
      selectedDiscipline: "",
      sourceKind: "all",
      sourceQuery: "",
      selectedOnly: false,
      pickerMode: "source",
      sourceRenderCount: 120,
      page: 1,
      viewMode: "daily",
      hasMore: false,
      currentItems: [],
      details: new Set(),
      sourceCounts: new Map(),
      crawlInFlight: false,
      translationInFlight: false,
      libraryViewInFlight: false,
      aiFilterInFlight: false,
      aiFilterActive: false,
      aiFilterQuery: "",
      aiFilterResults: new Map(),
      ragIndexInFlight: false,
      ragAskInFlight: false,
      ragResult: null,
      detailTranslationInFlightIds: new Set(),
      allItems: [],
      relatedPapers: new Map(),
      relatedInFlightIds: new Set(),
      readKeys: new Set(),
      favoriteKeys: new Set(),
      hiddenKeys: new Set(),
      selectedKeys: new Set(),
      hideRead: false,
      libraryAvailable: true,
      savedViews: [],
      preferenceProfile: null,
      preferenceSettings: {
        learning_enabled: true,
        query_history_enabled: true,
        model_signal_learning_enabled: true,
        auto_purify_enabled: true,
      },
      preferenceInFlight: false,
      lastActiveSources: 0,
      translations: new Map(),
      detailTranslations: new Map(),
      enrichments: new Map(),
    };

    const $ = (id) => document.getElementById(id);
    const sourceKindLabels = {
      all: "全部",
      preprint: "预印本",
      journal: "期刊",
      metadata: "资料库",
      working_papers: "工作论文",
      news: "新闻",
      local: "本地",
      other: "其他",
    };
    const disciplineAliases = {
      engineering: ["工学", "工程技术", "工程学"],
      computer_science: ["计算机", "AI", "人工智能"],
      mathematics: ["统计", "数学统计"],
      economics: ["金融"],
      life_science: ["生物", "生命"],
      earth_science: ["地学", "地球"],
    };

    function loadStoredSet(key) {
      try {
        const raw = JSON.parse(localStorage.getItem(key) || "[]");
        return new Set(Array.isArray(raw) ? raw.filter(Boolean).map(String) : []);
      } catch (_) {
        return new Set();
      }
    }
    function saveStoredSet(key, values) {
      try {
        localStorage.setItem(key, JSON.stringify(Array.from(values)));
      } catch (_) {}
    }
    function loadStoredBool(key) {
      try {
        return localStorage.getItem(key) === "1";
      } catch (_) {
        return false;
      }
    }
    function saveStoredBool(key, value) {
      try {
        localStorage.setItem(key, value ? "1" : "0");
      } catch (_) {}
    }
    function initReadingState() {
      state.readKeys = loadStoredSet(READ_STORAGE_KEY);
      state.favoriteKeys = loadStoredSet(FAVORITE_STORAGE_KEY);
      state.hiddenKeys = loadStoredSet(HIDDEN_STORAGE_KEY);
      state.hideRead = loadStoredBool(HIDE_READ_STORAGE_KEY);
    }
    function initPreferenceState() {}

    function pad(n) { return String(n).padStart(2, "0"); }
    function dateOnly(date) {
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    }
    function addDays(value, days) {
      const [y, m, d] = value.split("-").map(Number);
      const date = new Date(y, m - 1, d);
      date.setDate(date.getDate() + days);
      return dateOnly(date);
    }
    function dateRangeDayCount(startValue, endValue) {
      if (!startValue || !endValue) return 0;
      const [sy, sm, sd] = startValue.split("-").map(Number);
      const [ey, em, ed] = endValue.split("-").map(Number);
      const cursor = new Date(sy, sm - 1, sd);
      const end = new Date(ey, em - 1, ed);
      if (Number.isNaN(cursor.getTime()) || Number.isNaN(end.getTime()) || cursor > end) return 0;
      return Math.floor((end.getTime() - cursor.getTime()) / 86400000) + 1;
    }
    function fmtDay(value) {
      if (!value) return "";
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return "";
      return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function safeExternalUrl(value) {
      const raw = String(value || "").trim();
      if (!raw) return "";
      try {
        const url = new URL(raw);
        return ["http:", "https:"].includes(url.protocol) ? url.href : "";
      } catch (_) {
        return "";
      }
    }
    function externalLink(value, label) {
      const url = safeExternalUrl(value);
      return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>` : "";
    }
    function arxivIdentifier(value) {
      const match = String(value || "").match(/(?:arxiv(?:\.org\/abs\/|:)?\s*)?(\d{4}\.\d{4,5}(?:v\d+)?)/i);
      return match ? match[1] : "";
    }
    function paperIdentifierLabel(paper) {
      const doi = String(paper?.doi || "").trim();
      if (doi) return `DOI ${doi}`;
      const id = String(paper?.id || "").trim();
      const dailySources = Array.isArray(paper?._daily_sources) ? paper._daily_sources : [];
      const sourceText = [paper?.source, paper?.source_type, paper?._daily_source, ...dailySources]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const arxivId = arxivIdentifier(id) || arxivIdentifier(paper?.url);
      if (arxivId || sourceText.includes("arxiv")) {
        return `arXiv ${arxivId || id.replace(/^arxiv\s*:/i, "").trim()}`;
      }
      return id ? `ID ${id}` : "";
    }
    function toast(message) {
      $("toast").textContent = message;
      $("toast").classList.add("show");
      window.clearTimeout(toast.timer);
      toast.timer = window.setTimeout(() => $("toast").classList.remove("show"), 2400);
    }

    function today() {
      const now = new Date();
      $("dateFrom").value = dateOnly(now);
      $("dateTo").value = dateOnly(now);
    }
    function thisWeek() {
      const now = new Date();
      const day = now.getDay() || 7;
      const start = new Date(now);
      start.setDate(now.getDate() - day + 1);
      $("dateFrom").value = dateOnly(start);
      $("dateTo").value = dateOnly(now);
    }
