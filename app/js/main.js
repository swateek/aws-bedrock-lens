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
    scopeChip: $("scope-chip"),
    themeToggle: $("theme-toggle"),
    search: $("search"),
    filterProvider: $("filter-provider"),
    filterRegion: $("filter-region"),
    filterTier: $("filter-tier"),
    filterType: $("filter-type"),
    filterHasPricing: $("filter-has-pricing"),
    filtersToggle: $("filters-toggle"),
    filtersPanel: $("filters-panel"),
    filtersBackdrop: $("filters-backdrop"),
    filtersDone: $("filters-done"),
    filtersCount: $("filters-count"),
    modelList: $("model-list"),
    browserView: $("browser-view"),
    compareView: $("compare-view"),
    compareThead: $("compare-thead"),
    compareTbody: $("compare-tbody"),
    compareBar: $("compare-bar"),
    compareBtn: $("compare-btn"),
    compareCount: $("compare-count"),
    backBtn: $("back-btn"),
    blendControl: $("blend-control"),
  };

  let catalog = { meta: {}, scrape: {}, models: [] };
  const selected = new Set();

  function loadBlend() {
    try {
      const raw = sessionStorage.getItem("bedrock-lens-blend");
      if (raw === "1:1" || raw === "1:3" || raw === "1:5") return raw;
    } catch {
      /* ignore */
    }
    return "1:3";
  }

  function parseBlend(ratio) {
    const [a, b] = String(ratio).split(":").map(Number);
    return { blendIn: a || 1, blendOut: b || 3 };
  }

  function defaultPriceRegion() {
    return catalog.meta?.default_price_region || "us-east-1";
  }

  /** Availability region drives pricing; empty ("All") → catalog default. */
  function priceRegionFromFilter() {
    return els.filterRegion.value || defaultPriceRegion();
  }

  function initPriceScope() {
    const blend = parseBlend(loadBlend());
    global.BedrockLens._priceScope = {
      region: defaultPriceRegion(),
      tier: "on_demand",
      ...blend,
    };
  }

  function syncPriceScopeFromControls() {
    global.BedrockLens._priceScope.region = priceRegionFromFilter();
    global.BedrockLens._priceScope.tier = els.filterTier.value || "on_demand";
  }

  function filters() {
    return {
      search: els.search.value,
      provider: els.filterProvider.value,
      region: els.filterRegion.value,
      tier: els.filterTier.value || "on_demand",
      type: els.filterType.value,
      hasPricing: els.filterHasPricing?.value || "",
    };
  }

  function refreshList() {
    syncPriceScopeFromControls();
    global.BedrockLens.browser.renderModelList(
      catalog,
      selected,
      filters(),
      els.modelList,
      onToggle,
    );
    global.BedrockLens.browser.updateFiltersToggle(els, filters());
    global.BedrockLens.browser.updateMetaUI(catalog, els);
  }

  function onToggle(modelId) {
    const wasSelected = selected.has(modelId);
    if (wasSelected) selected.delete(modelId);
    else selected.add(modelId);
    global.BedrockLens.util.trackEvent("model_toggle", {
      model_id: modelId,
      selected: !wasSelected,
      count: selected.size,
    });
    global.BedrockLens.urlState.syncToUrl(selected);
    global.BedrockLens.browser.updateCompareBar(selected, els);
    refreshList();
  }

  function showBrowser() {
    global.BedrockLens.util.trackEvent("back_to_browser", {});
    selected.clear();
    global.BedrockLens.urlState.syncToUrl(selected);
    global.BedrockLens.browser.updateCompareBar(selected, els);
    els.browserView.hidden = false;
    els.compareView.hidden = true;
    els.compareView.classList.add("view--hidden");
    refreshList();
    global.BedrockLens.util.pinFavicon();
    els.search.focus();
  }

  function syncBlendButtons() {
    const ratio = `${global.BedrockLens._priceScope.blendIn}:${global.BedrockLens._priceScope.blendOut}`;
    document.querySelectorAll(".blend-preset").forEach((btn) => {
      btn.classList.toggle(
        "blend-preset--active",
        btn.getAttribute("data-ratio") === ratio,
      );
    });
  }

  function showCompare() {
    if (selected.size < 1) return;
    syncPriceScopeFromControls();
    global.BedrockLens.util.trackEvent("compare_open", {
      model_count: selected.size,
    });
    const models = catalog.models.filter((m) => selected.has(m.model_id));
    const allToken = models.every((m) => m.pricing_type === "token");
    if (els.blendControl) els.blendControl.hidden = !allToken;
    syncBlendButtons();
    els.browserView.hidden = true;
    els.compareView.hidden = false;
    els.compareView.classList.remove("view--hidden");
    global.BedrockLens.compare.renderCompareTable(
      models,
      els.compareThead,
      els.compareTbody,
    );
    global.BedrockLens.util.pinFavicon();
    els.backBtn.focus();
  }

  function onRegionOrTierChange() {
    const region = priceRegionFromFilter();
    global.BedrockLens.browser.populateTierFilter(
      catalog,
      els.filterTier,
      region,
    );
    syncPriceScopeFromControls();
    refreshList();
    if (!els.compareView.hidden) showCompare();
  }

  function bindEvents() {
    els.search.addEventListener("input", refreshList);
    els.filterProvider.addEventListener("change", () => {
      global.BedrockLens.util.trackEvent("filter_provider_change", {
        provider: els.filterProvider.value,
      });
      refreshList();
    });
    els.filterRegion.addEventListener("change", () => {
      global.BedrockLens.util.trackEvent("filter_region_change", {
        region: els.filterRegion.value,
      });
      onRegionOrTierChange();
    });
    els.filterType.addEventListener("change", () => {
      global.BedrockLens.util.trackEvent("filter_type_change", {
        type: els.filterType.value,
      });
      refreshList();
    });
    if (els.filterHasPricing) {
      els.filterHasPricing.addEventListener("change", () => {
        global.BedrockLens.util.trackEvent("filter_has_pricing_change", {
          value: els.filterHasPricing.value,
        });
        refreshList();
      });
    }
    els.filterTier.addEventListener("change", onRegionOrTierChange);

    if (els.filtersToggle && els.filtersPanel) {
      const isFiltersSheetMode = () =>
        window.matchMedia("(max-width: 600px)").matches;

      const setFiltersOpen = (open) => {
        if (!isFiltersSheetMode()) return;
        els.filtersPanel.classList.toggle("filters-panel--open", open);
        els.filtersToggle.setAttribute(
          "aria-expanded",
          open ? "true" : "false",
        );
        document.body.classList.toggle("filters-sheet-open", open);
        if (els.filtersBackdrop) {
          els.filtersBackdrop.hidden = !open;
        }
        if (open) {
          const focusTarget = els.filtersDone || els.filterRegion;
          if (focusTarget) focusTarget.focus();
        } else {
          els.filtersToggle.focus();
        }
      };

      els.filtersToggle.addEventListener("click", () => {
        if (!isFiltersSheetMode()) return;
        const open = !els.filtersPanel.classList.contains(
          "filters-panel--open",
        );
        setFiltersOpen(open);
      });

      if (els.filtersDone) {
        els.filtersDone.addEventListener("click", () => setFiltersOpen(false));
      }
      if (els.filtersBackdrop) {
        els.filtersBackdrop.addEventListener("click", () =>
          setFiltersOpen(false),
        );
      }
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (!els.filtersPanel.classList.contains("filters-panel--open")) {
          return;
        }
        setFiltersOpen(false);
      });

      window
        .matchMedia("(max-width: 600px)")
        .addEventListener("change", (e) => {
          if (e.matches) return;
          els.filtersPanel.classList.remove("filters-panel--open");
          els.filtersToggle.setAttribute("aria-expanded", "false");
          document.body.classList.remove("filters-sheet-open");
          if (els.filtersBackdrop) els.filtersBackdrop.hidden = true;
        });
    }

    if (els.themeToggle) {
      global.BedrockLens.util.updateThemeToggle(els.themeToggle);
      els.themeToggle.addEventListener("click", () => {
        const next = global.BedrockLens.util.cycleTheme();
        global.BedrockLens.util.updateThemeToggle(els.themeToggle);
        global.BedrockLens.util.trackEvent("theme_toggle", { theme: next });
      });
    }

    document.querySelectorAll(".blend-preset").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ratio = btn.getAttribute("data-ratio");
        const parsed = parseBlend(ratio);
        Object.assign(global.BedrockLens._priceScope, parsed);
        try {
          sessionStorage.setItem("bedrock-lens-blend", ratio);
        } catch {
          /* ignore */
        }
        syncBlendButtons();
        if (!els.compareView.hidden) showCompare();
      });
    });

    els.compareBtn.addEventListener("click", showCompare);
    els.backBtn.addEventListener("click", showBrowser);
  }

  async function init() {
    global.BedrockLens.util.pinFavicon();
    initPriceScope();
    if (els.themeToggle) {
      global.BedrockLens.util.updateThemeToggle(els.themeToggle);
    }

    try {
      catalog = await global.BedrockLens.catalog.loadCatalog();
    } catch (err) {
      els.modelList.innerHTML = `<li class="empty-state">Failed to load pricing data: ${global.BedrockLens.util.escapeHtml(err.message)}</li>`;
      return;
    }

    global.BedrockLens._priceScope.region = defaultPriceRegion();

    global.BedrockLens.browser.updateMetaUI(catalog, els);
    global.BedrockLens.browser.populateProviderFilter(
      catalog,
      els.filterProvider,
    );
    global.BedrockLens.browser.populateRegionFilter(catalog, els.filterRegion);
    global.BedrockLens.browser.populateTierFilter(
      catalog,
      els.filterTier,
      priceRegionFromFilter(),
    );
    syncPriceScopeFromControls();

    const validIds = new Set(catalog.models.map((m) => m.model_id));
    const fromUrl = global.BedrockLens.urlState.parseSelection(
      global.location.search,
      validIds,
    );
    for (const id of fromUrl) selected.add(id);

    global.BedrockLens.browser.updateCompareBar(selected, els);
    refreshList();
    bindEvents();
  }

  init();
})(window);
