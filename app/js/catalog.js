/**
 * @file Load, normalize, and expose the pricing catalog.
 */
(function (global) {
  "use strict";

  const { getDataBase, pricingJsonUrl } = global.BedrockLens.CONSTANTS;

  function normalizeOnDemand(model) {
    const type = model.pricing_type;
    const base = {
      input_per_1k: null,
      output_per_1k: null,
      standard_per_image: null,
      premium_per_image: null,
    };
    const incoming = model.on_demand || {};
    for (const key of Object.keys(base)) {
      if (key in incoming) base[key] = incoming[key];
    }
    if (type === "embedding") base.output_per_1k = null;
    return base;
  }

  function normalizeCatalog(raw) {
    const catalog = {
      meta: {
        schema_version: String(raw.meta?.schema_version || "2"),
        source: raw.meta?.source || "",
        last_scraped_at:
          raw.meta?.last_scraped_at ?? raw.meta?.last_updated ?? null,
        pricing_updated_at:
          raw.meta?.pricing_updated_at ?? raw.meta?.last_updated ?? null,
        parser_version: raw.meta?.parser_version || "—",
      },
      scrape: {
        models_matched: raw.scrape?.models_matched ?? 0,
        models_in_catalog:
          raw.scrape?.models_in_catalog ?? (raw.models?.length || 0),
        coverage_pct: raw.scrape?.coverage_pct ?? 0,
        warnings: raw.scrape?.warnings || [],
      },
      models: (raw.models || []).map((m) => ({
        ...m,
        pricing_source: m.pricing_source || "manual",
        on_demand: normalizeOnDemand(m),
      })),
    };
    catalog.scrape.models_in_catalog = catalog.models.length;
    return catalog;
  }

  function loadEmbedScript() {
    return new Promise((resolve, reject) => {
      if (global.PRICING_DATA) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = global.BedrockLens.CONSTANTS.pricingEmbedUrl();
      script.onload = () => resolve();
      script.onerror = () =>
        reject(new Error("Failed to load pricing.embed.js"));
      document.head.appendChild(script);
    });
  }

  async function loadCatalog() {
    try {
      const res = await fetch(pricingJsonUrl());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      return normalizeCatalog(raw);
    } catch (fetchErr) {
      try {
        await loadEmbedScript();
      } catch {
        throw fetchErr;
      }
      if (typeof global.PRICING_DATA === "undefined") {
        throw new Error("Could not load pricing data");
      }
      return normalizeCatalog(global.PRICING_DATA);
    }
  }

  global.BedrockLens.catalog = {
    loadCatalog,
    normalizeCatalog,
  };
})(window);
