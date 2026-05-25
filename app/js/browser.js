/**
 * @file Model list, filters, and selection UI.
 */
(function (global) {
  "use strict";

  const { escapeHtml, escapeAttr, formatRelativeDate, daysSince } =
    global.BedrockLens.util;
  const { formatListPrice } = global.BedrockLens.compare;
  const { STALE_DAYS } = global.BedrockLens.CONSTANTS;

  function updateMetaUI(catalog, els) {
    const pricingAt = catalog.meta.pricing_updated_at;
    const scrapedAt = catalog.meta.last_scraped_at;
    const parts = [];
    if (pricingAt) {
      parts.push(`pricing updated ${formatRelativeDate(pricingAt)}`);
    }
    if (scrapedAt) {
      parts.push(`scraped ${formatRelativeDate(scrapedAt)}`);
    }
    els.lastUpdated.textContent = parts.length ? parts.join(" · ") : "—";

    const staleDays = pricingAt ? daysSince(pricingAt) : null;
    if (staleDays != null && staleDays > STALE_DAYS) {
      els.stalenessBanner.hidden = false;
      els.stalenessDate.textContent = formatRelativeDate(pricingAt);
    } else {
      els.stalenessBanner.hidden = true;
    }

    const { scrape } = catalog;
    if (scrape && els.coverageBanner) {
      const low = scrape.coverage_pct < 50;
      els.coverageBanner.hidden = !low && scrape.warnings.length === 0;
      if (!els.coverageBanner.hidden) {
        const warn =
          scrape.warnings.length > 0
            ? scrape.warnings[0]
            : "Most prices are manually curated.";
        els.coverageText.textContent = `Automated scrape covers ${scrape.models_matched}/${scrape.models_in_catalog} models (${scrape.coverage_pct}%). ${warn}`;
      }
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

  function getFilteredModels(catalog, filters) {
    const q = filters.search.trim().toLowerCase();
    const { provider, type } = filters;

    return catalog.models.filter((m) => {
      if (provider && m.provider !== provider) return false;
      if (type && m.pricing_type !== type) return false;
      if (q) {
        const hay =
          `${m.display_name} ${m.provider} ${m.model_id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
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
      const sourceBadge =
        model.pricing_source === "auto"
          ? '<span class="badge badge--auto">auto</span>'
          : '<span class="badge badge--manual">manual</span>';

      li.innerHTML = `
        <input type="checkbox" class="model-card__check" ${checked ? "checked" : ""} aria-label="Select ${escapeAttr(model.display_name)}">
        <div class="model-card__main">
          <div class="model-card__row">
            <span class="model-card__name">${escapeHtml(model.display_name)}</span>
            <span class="model-card__provider" data-provider="${escapeAttr(model.provider)}">${escapeHtml(model.provider)}</span>
            ${sourceBadge}
          </div>
          <div class="model-card__meta">${escapeHtml(formatListPrice(model))}</div>
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
  }

  global.BedrockLens.browser = {
    updateMetaUI,
    populateProviderFilter,
    getFilteredModels,
    renderModelList,
    updateCompareBar,
  };
})(window);
