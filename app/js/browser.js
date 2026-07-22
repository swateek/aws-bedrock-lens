/**
 * @file Model list, filters, and selection UI.
 */
(function (global) {
  "use strict";

  const {
    escapeHtml,
    escapeAttr,
    formatRelativeDate,
    daysSince,
    modelHasPrice,
    formatScopeChip,
  } = global.BedrockLens.util;
  const { formatListPrice } = global.BedrockLens.compare;
  const { STALE_DAYS } = global.BedrockLens.CONSTANTS;

  function updateMetaUI(catalog, els) {
    const pricingAt = catalog.meta.pricing_updated_at;
    els.lastUpdated.textContent = pricingAt
      ? `pricing updated ${formatRelativeDate(pricingAt)}`
      : "—";

    const staleDays = pricingAt ? daysSince(pricingAt) : null;
    if (staleDays != null && staleDays > STALE_DAYS) {
      els.stalenessBanner.hidden = false;
      els.stalenessDate.textContent = formatRelativeDate(pricingAt);
    } else {
      els.stalenessBanner.hidden = true;
    }

    const { scrape } = catalog;
    if (scrape && els.coverageBanner) {
      const lowPrice = (scrape.price_coverage_pct ?? 0) < 50;
      const show =
        lowPrice ||
        scrape.warnings.some((w) => !w.startsWith("Unmapped pricing page row"));
      els.coverageBanner.hidden = !show;
      if (!els.coverageBanner.hidden) {
        const priced = scrape.models_with_prices ?? 0;
        const total = scrape.models_in_catalog ?? catalog.models.length;
        const known = scrape.models_known_to_aws ?? total;
        const detail = `${priced}/${total} models have list prices (${scrape.price_coverage_pct ?? 0}%). ${known} foundation models known to AWS.`;
        els.coverageText.textContent = detail;
      }
    }

    if (els.scopeChip) {
      const s = global.BedrockLens._priceScope || {};
      els.scopeChip.textContent = formatScopeChip(s.region, s.tier);
    }
  }

  function populateProviderFilter(catalog, select) {
    const providers = [
      ...new Set(catalog.models.map((m) => m.provider)),
    ].sort();
    while (select.options.length > 1) select.remove(1);
    for (const p of providers) {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      select.appendChild(opt);
    }
  }

  function populateRegionFilter(catalog, select) {
    // Availability only — do not mix in priced-region keys
    const regions = [
      ...new Set(catalog.models.flatMap((m) => m.regions || [])),
    ].sort();
    while (select.options.length > 1) select.remove(1);
    for (const r of regions) {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r;
      select.appendChild(opt);
    }
  }

  function populateTierFilter(catalog, select, region) {
    const defaultRegion = catalog.meta?.default_price_region || "us-east-1";
    const r = region || defaultRegion;
    const tiers = new Set(["on_demand"]);
    for (const m of catalog.models) {
      // Prefer selected region; also surface tiers from default if browsing All
      const sources = [m.list_prices?.[r] || {}];
      if (r !== defaultRegion) {
        sources.push(m.list_prices?.[defaultRegion] || {});
      }
      for (const regionTiers of sources) {
        for (const [t, slice] of Object.entries(regionTiers)) {
          if (
            global.BedrockLens.util.sliceHasPrice(slice) &&
            !t.startsWith("cache")
          ) {
            tiers.add(t);
          }
        }
      }
    }
    const order = [
      "on_demand",
      "on_demand_global",
      "batch",
      "batch_global",
      "flex",
      "priority",
    ];
    const sorted = [...tiers].sort(
      (a, b) =>
        (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
        (order.indexOf(b) === -1 ? 99 : order.indexOf(b)),
    );
    const prev = select.value;
    select.innerHTML = "";
    for (const t of sorted) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = global.BedrockLens.util.formatTierLabel(t);
      select.appendChild(opt);
    }
    if (sorted.includes(prev)) select.value = prev;
    else select.value = "on_demand";
  }

  function getFilteredModels(catalog, filters) {
    const q = filters.search.trim().toLowerCase();
    const { provider, region, type, hasPricing } = filters;
    const priceRegion =
      global.BedrockLens._priceScope?.region ||
      catalog.meta?.default_price_region ||
      "us-east-1";
    const priceTier = global.BedrockLens._priceScope?.tier || "on_demand";

    return catalog.models.filter((m) => {
      if (provider && m.provider !== provider) return false;
      if (region && !(m.regions || []).includes(region)) return false;
      if (type && m.pricing_type !== type) return false;
      const has = modelHasPrice(m, priceRegion, priceTier);
      if (hasPricing === "yes" && !has) return false;
      if (hasPricing === "no" && has) return false;
      if (q) {
        const hay =
          `${m.display_name} ${m.provider} ${m.model_id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function activeFilterCount(filters) {
    let n = 0;
    if (filters.provider) n += 1;
    if (filters.type) n += 1;
    if (filters.hasPricing) n += 1;
    return n;
  }

  function updateFiltersToggle(els, filters) {
    if (!els.filtersToggle || !els.filtersCount) return;
    const n = activeFilterCount(filters);
    els.filtersCount.hidden = n === 0;
    els.filtersCount.textContent = String(n);
  }

  function renderModelList(catalog, selected, filters, listEl, onToggle) {
    const models = getFilteredModels(catalog, filters);
    listEl.innerHTML = "";

    if (models.length === 0) {
      const li = document.createElement("li");
      li.className = "empty-state";
      li.textContent = "No models match your filters.";
      listEl.appendChild(li);
      return;
    }

    for (const model of models) {
      const li = document.createElement("li");
      li.className = "model-card";
      li.dataset.modelId = model.model_id;
      if (selected.has(model.model_id)) {
        li.classList.add("model-card--selected");
      }

      const checked = selected.has(model.model_id);
      const previewBadge =
        model.availability === "preview"
          ? '<span class="badge badge--preview">preview</span>'
          : "";
      const s = global.BedrockLens._priceScope || {};
      const has = modelHasPrice(model, s.region, s.tier);
      const priceClass = has ? "" : " model-card__meta--unknown";

      li.innerHTML = `
        <input type="checkbox" class="model-card__check" ${checked ? "checked" : ""} aria-label="Select ${escapeAttr(model.display_name)}">
        <div class="model-card__main">
          <div class="model-card__row">
            <span class="model-card__name">${escapeHtml(model.display_name)}</span>
            <span class="model-card__provider" data-provider="${escapeAttr(model.provider)}">${escapeHtml(model.provider)}</span>
            ${previewBadge}
          </div>
          <div class="model-card__meta${priceClass}">${escapeHtml(formatListPrice(model))}</div>
          <span class="model-card__id">${escapeHtml(model.model_id)}</span>
        </div>
      `;

      li.addEventListener("click", (e) => {
        if (e.target.classList.contains("model-card__check")) return;
        onToggle(model.model_id);
      });

      const cb = li.querySelector(".model-card__check");
      cb.addEventListener("click", (e) => {
        e.stopPropagation();
        onToggle(model.model_id);
      });

      listEl.appendChild(li);
    }
  }

  function updateCompareBar(selected, els) {
    const n = selected.size;
    els.compareCount.textContent = String(n);
    els.compareBar.hidden = n < 1;
    document.body.classList.toggle("has-compare-bar", n >= 1);
  }

  global.BedrockLens.browser = {
    updateMetaUI,
    populateProviderFilter,
    populateRegionFilter,
    populateTierFilter,
    getFilteredModels,
    renderModelList,
    updateCompareBar,
    updateFiltersToggle,
    activeFilterCount,
  };
})(window);
