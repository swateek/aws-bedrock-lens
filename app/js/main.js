/**
 * @file Application entry point.
 */
(function (global) {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    stalenessBanner: $("staleness-banner"),
    stalenessDate: $("staleness-date"),
    coverageBanner: $("coverage-banner"),
    coverageText: $("coverage-text"),
    lastUpdated: $("last-updated"),
    search: $("search"),
    filterProvider: $("filter-provider"),
    filterType: $("filter-type"),
    modelList: $("model-list"),
    browserView: $("browser-view"),
    compareView: $("compare-view"),
    compareThead: $("compare-thead"),
    compareTbody: $("compare-tbody"),
    compareBar: $("compare-bar"),
    compareBtn: $("compare-btn"),
    compareCount: $("compare-count"),
    backBtn: $("back-btn"),
  };

  let catalog = { meta: {}, scrape: {}, models: [] };
  const selected = new Set();

  function filters() {
    return {
      search: els.search.value,
      provider: els.filterProvider.value,
      type: els.filterType.value,
    };
  }

  function refreshList() {
    global.BedrockLens.browser.renderModelList(
      catalog,
      selected,
      filters(),
      els.modelList,
      onToggle
    );
  }

  function onToggle(modelId) {
    if (selected.has(modelId)) selected.delete(modelId);
    else selected.add(modelId);
    global.BedrockLens.urlState.syncToUrl(selected);
    global.BedrockLens.browser.updateCompareBar(selected, els);
    refreshList();
  }

  function showBrowser() {
    els.browserView.hidden = false;
    els.compareView.hidden = true;
    els.compareView.classList.add("view--hidden");
    els.compareBtn.focus();
  }

  function showCompare() {
    if (selected.size < 1) return;
    const models = catalog.models.filter((m) => selected.has(m.model_id));
    els.browserView.hidden = true;
    els.compareView.hidden = false;
    els.compareView.classList.remove("view--hidden");
    global.BedrockLens.compare.renderCompareTable(
      models,
      els.compareThead,
      els.compareTbody
    );
    els.backBtn.focus();
  }

  function bindEvents() {
    els.search.addEventListener("input", refreshList);
    els.filterProvider.addEventListener("change", refreshList);
    els.filterType.addEventListener("change", refreshList);
    els.compareBtn.addEventListener("click", showCompare);
    els.backBtn.addEventListener("click", showBrowser);
  }

  async function init() {
    try {
      catalog = await global.BedrockLens.catalog.loadCatalog();
    } catch (err) {
      els.modelList.innerHTML = `<li class="empty-state">Failed to load pricing data: ${global.BedrockLens.util.escapeHtml(err.message)}</li>`;
      return;
    }

    global.BedrockLens.browser.updateMetaUI(catalog, els);
    global.BedrockLens.browser.populateProviderFilter(catalog, els.filterProvider);

    const validIds = new Set(catalog.models.map((m) => m.model_id));
    const fromUrl = global.BedrockLens.urlState.parseSelection(
      global.location.search,
      validIds
    );
    for (const id of fromUrl) selected.add(id);

    global.BedrockLens.browser.updateCompareBar(selected, els);
    refreshList();
    bindEvents();
  }

  init();
})(window);
