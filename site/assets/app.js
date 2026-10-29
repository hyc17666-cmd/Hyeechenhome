const SOURCE_META = {
  all: { name: "全部", order: 0 },
  beijing: { name: "北京日报", order: 1 },
  guangming: { name: "光明日报", order: 2 },
  economic: { name: "经济日报", order: 3 }
};

const state = {
  data: null,
  articles: [],
  filtered: [],
  selectedDate: "",
  selectedSource: "all",
  selectedSection: "all",
  query: ""
};

const elements = {
  updateTime: document.querySelector("#updateTime"),
  totalCount: document.querySelector("#totalCount"),
  sourceCount: document.querySelector("#sourceCount"),
  paperDate: document.querySelector("#paperDate"),
  dataStatus: document.querySelector("#dataStatus"),
  searchInput: document.querySelector("#searchInput"),
  dateSelect: document.querySelector("#dateSelect"),
  sectionSelect: document.querySelector("#sectionSelect"),
  clearButton: document.querySelector("#clearButton"),
  sourceTabs: document.querySelector("#sourceTabs"),
  resultCount: document.querySelector("#resultCount"),
  resultsTitle: document.querySelector("#resultsTitle"),
  articleGrid: document.querySelector("#articleGrid"),
  emptyState: document.querySelector("#emptyState"),
  toast: document.querySelector("#toast")
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${year}年${Number(month)}月${Number(day)}日`;
}

function formatDateTime(value) {
  if (!value) return "更新时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date).replaceAll("/", "-");
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
  }, 2600);
}

function uniqueDates(articles) {
  return [...new Set(articles.map(article => article.paper_date).filter(Boolean))]
    .sort((a, b) => b.localeCompare(a));
}

function dateArticles() {
  return state.articles.filter(article => article.paper_date === state.selectedDate);
}

function renderDateSelect() {
  const dates = uniqueDates(state.articles);
  if (!dates.length) {
    elements.dateSelect.innerHTML = '<option value="">暂无数据</option>';
    return;
  }
  if (!dates.includes(state.selectedDate)) state.selectedDate = dates[0];
  elements.dateSelect.innerHTML = dates.map(value => (
    `<option value="${escapeHtml(value)}"${value === state.selectedDate ? " selected" : ""}>${escapeHtml(formatDate(value))}</option>`
  )).join("");
}

function renderSourceTabs() {
  const articles = dateArticles();
  const counts = { all: articles.length };
  for (const key of Object.keys(SOURCE_META)) {
    if (key === "all") continue;
    counts[key] = articles.filter(article => article.source_key === key).length;
  }

  const keys = ["all", "beijing", "guangming", "economic"];
  elements.sourceTabs.innerHTML = keys.map(key => {
    const meta = SOURCE_META[key];
    const isActive = state.selectedSource === key;
    const activeClass = isActive ? " active" : "";
    return `<button class="source-tab${activeClass}" type="button" data-source="${key}" aria-pressed="${isActive ? "true" : "false"}">
      ${escapeHtml(meta.name)}<span class="tab-count">${counts[key]}</span>
    </button>`;
  }).join("");

  elements.sourceTabs.querySelectorAll(".source-tab").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedSource = button.dataset.source;
      state.selectedSection = "all";
      render();
    });
  });
}

function renderSectionSelect() {
  const pool = dateArticles().filter(article => (
    state.selectedSource === "all" || article.source_key === state.selectedSource
  ));
  const sections = [...new Set(pool.map(article => article.section).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "zh-CN"));
  if (state.selectedSection !== "all" && !sections.includes(state.selectedSection)) {
    state.selectedSection = "all";
  }
  elements.sectionSelect.innerHTML = [
    '<option value="all">全部栏目</option>',
    ...sections.map(value => `<option value="${escapeHtml(value)}"${value === state.selectedSection ? " selected" : ""}>${escapeHtml(value)}</option>`)
  ].join("");
}

function applyFilters() {
  const query = state.query.trim().toLocaleLowerCase("zh-CN");
  state.filtered = state.articles.filter(article => {
    if (article.paper_date !== state.selectedDate) return false;
    if (state.selectedSource !== "all" && article.source_key !== state.selectedSource) return false;
    if (state.selectedSection !== "all" && article.section !== state.selectedSection) return false;
    if (query && !article.title.toLocaleLowerCase("zh-CN").includes(query)) return false;
    return true;
  });

  state.filtered.sort((a, b) => {
    const sourceDiff = (SOURCE_META[a.source_key]?.order ?? 99) - (SOURCE_META[b.source_key]?.order ?? 99);
    if (sourceDiff) return sourceDiff;
    const pageDiff = (a.page ?? 999) - (b.page ?? 999);
    if (pageDiff) return pageDiff;
    const positionDiff = (a.position ?? 9999) - (b.position ?? 9999);
    if (positionDiff) return positionDiff;
    return a.title.localeCompare(b.title, "zh-CN");
  });
}

function renderStats() {
  const current = dateArticles();
  const representedSources = new Set(current.map(article => article.source_key)).size;
  elements.totalCount.textContent = String(current.length);
  elements.sourceCount.textContent = String(representedSources);
  elements.paperDate.textContent = formatDate(state.selectedDate) || "--";

  const failed = (state.data.sources_status || []).filter(item => item.status === "error");
  if (failed.length) {
    elements.dataStatus.textContent = `${failed.length} 家来源更新异常`;
  } else if (current.length) {
    elements.dataStatus.textContent = "更新正常";
  } else {
    elements.dataStatus.textContent = "暂无当日数据";
  }
}

function articleCard(article) {
  const sourceLabel = SOURCE_META[article.source_key]?.name || article.source_name || "报纸";
  const pageLabel = article.page ? `第${article.page}版` : "";
  const sectionLabel = article.section || "未分类";
  return `<a class="article-card source-${escapeHtml(article.source_key)}"
      href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
    <div class="card-top">
      <span class="source-badge">${escapeHtml(sourceLabel)}</span>
      ${pageLabel ? `<span class="page-badge">${escapeHtml(pageLabel)}</span>` : ""}
      <span class="section-badge">${escapeHtml(sectionLabel)}</span>
    </div>
    <h3>${escapeHtml(article.title)}</h3>
    <div class="card-bottom">
      <span class="date-badge">${escapeHtml(formatDate(article.paper_date))}</span>
      <span class="read-link">阅读原文 ↗</span>
    </div>
  </a>`;
}

function renderArticles() {
  applyFilters();
  const count = state.filtered.length;
  elements.resultCount.textContent = `${count} 条`;
  elements.resultsTitle.textContent = state.selectedSource === "all"
    ? "今日文章"
    : `${SOURCE_META[state.selectedSource].name} · 今日文章`;
  elements.articleGrid.innerHTML = state.filtered.map(articleCard).join("");
  elements.emptyState.hidden = count > 0;
  elements.articleGrid.hidden = count === 0;
}

function render() {
  renderSourceTabs();
  renderSectionSelect();
  renderStats();
  renderArticles();
}

async function loadData() {
  try {
    const response = await fetch(`data/articles.json?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.articles = (state.data.articles || []).filter(article => article.title && article.url && article.paper_date);
    state.selectedDate = uniqueDates(state.articles)[0] || "";
    state.selectedSource = "all";
    state.selectedSection = "all";
    state.query = "";

    // Optional shareable filters: ?source=guangming&section=要闻&q=关键词
    const params = new URLSearchParams(window.location.search);
    const requestedDate = params.get("date");
    if (requestedDate && uniqueDates(state.articles).includes(requestedDate)) {
      state.selectedDate = requestedDate;
    }
    const requestedSource = params.get("source");
    if (["beijing", "guangming", "economic"].includes(requestedSource)) {
      state.selectedSource = requestedSource;
    }
    const requestedSection = params.get("section");
    if (requestedSection) state.selectedSection = requestedSection;
    const requestedQuery = params.get("q");
    if (requestedQuery) {
      state.query = requestedQuery;
      elements.searchInput.value = requestedQuery;
    }

    elements.updateTime.textContent = `更新于 ${formatDateTime(state.data.generated_at)}`;
    renderDateSelect();
    render();

    const failed = (state.data.sources_status || []).filter(item => item.status === "error");
    if (failed.length) {
      showToast(`${failed.map(item => item.source_name).join("、")} 本次更新失败，已保留旧数据`);
    }
  } catch (error) {
    console.error(error);
    elements.updateTime.textContent = "数据读取失败";
    elements.dataStatus.textContent = "无法加载数据";
    elements.totalCount.textContent = "--";
    elements.sourceCount.textContent = "--";
    elements.paperDate.textContent = "--";
    elements.resultCount.textContent = "0 条";
    elements.articleGrid.innerHTML = "";
    elements.emptyState.hidden = false;
    elements.emptyState.querySelector("h3").textContent = "数据暂时无法加载";
    elements.emptyState.querySelector("p:last-child").textContent = "请稍后刷新页面，或检查 data/articles.json 是否存在。";
  }
}

elements.dateSelect.addEventListener("change", event => {
  state.selectedDate = event.target.value;
  state.selectedSource = "all";
  state.selectedSection = "all";
  state.query = "";
  elements.searchInput.value = "";
  render();
});

elements.sectionSelect.addEventListener("change", event => {
  state.selectedSection = event.target.value;
  renderSourceTabs();
  renderStats();
  renderArticles();
});

let searchTimer;
elements.searchInput.addEventListener("input", event => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    state.query = event.target.value;
    renderArticles();
  }, 150);
});

elements.clearButton.addEventListener("click", () => {
  state.selectedSource = "all";
  state.selectedSection = "all";
  state.query = "";
  elements.searchInput.value = "";
  render();
  elements.searchInput.focus();
});

loadData();
