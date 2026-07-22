/**
 * @file Load, normalize, and expose the pricing catalog.
 */
(function (global) {
  "use strict";

  const { pricingJsonUrl } = global.BedrockLens.CONSTANTS;

  function normalizeOnDemand(model) {
    const type = model.pricing_type;
    const base = {
      input_per_1m: null,
      output_per_1m: null,
      standard_per_image: null,
      premium_per_image: null,
      per_second: null,
      per_search_unit: null,
    };
    const incoming = model.on_demand || {};
    for (const key of Object.keys(base)) {
      if (key in incoming) base[key] = incoming[key];
    }
    if (type === "embedding") base.output_per_1m = null;
    return base;
  }

  function modelHasPrice(model) {
    return global.BedrockLens.util.modelHasPrice(model);
  }

  function ensureListPrices(model, defaultRegion) {
    const listPrices = model.list_prices || {};
    const region = defaultRegion || "us-east-1";
    if (!listPrices[region] && model.on_demand) {
      const od = normalizeOnDemand(model);
      if (Object.values(od).some((v) => v != null)) {
        listPrices[region] = { on_demand: { ...od } };
      }
    }
    return listPrices;
  }

  function normalizeCatalog(raw) {
    const defaultRegion =
      raw.meta?.default_price_region ||
      raw.meta?.price_list_region ||
      "us-east-1";

    const models = (raw.models || []).map((m) => {
      const onDemand = normalizeOnDemand(m);
      const listPrices = ensureListPrices(
        { ...m, on_demand: onDemand },
        defaultRegion,
      );
      return {
        ...m,
        pricing_source: m.pricing_source || "manual",
        availability: m.availability || "ga",
        alternate_ids: m.alternate_ids || [],
        on_demand: onDemand,
        list_prices: listPrices,
        _defaultPriceRegion: defaultRegion,
      };
    });

    const withPrices = models.filter(modelHasPrice).length;
    const inCatalog = models.length;
    const knownToAws = raw.meta?.models_known_to_aws ?? inCatalog;
    const derivedRegions = [
      ...new Set(models.flatMap((m) => Object.keys(m.list_prices || {}))),
    ].sort();
    const priceListRegions =
      raw.meta?.price_list_regions?.length > 0
        ? raw.meta.price_list_regions
        : derivedRegions.length
          ? derivedRegions
          : [defaultRegion];

    const catalog = {
      meta: {
        schema_version: String(raw.meta?.schema_version || "3.0"),
        source: raw.meta?.source || "",
        last_scraped_at:
          raw.meta?.last_scraped_at ?? raw.meta?.last_updated ?? null,
        pricing_updated_at:
          raw.meta?.pricing_updated_at ?? raw.meta?.last_updated ?? null,
        parser_version: raw.meta?.parser_version || "—",
        last_inventory_sync_at: raw.meta?.last_inventory_sync_at ?? null,
        models_known_to_aws: knownToAws,
        last_price_list_at: raw.meta?.last_price_list_at ?? null,
        price_list_region: defaultRegion,
        default_price_region: defaultRegion,
        price_list_regions: priceListRegions,
        products: raw.meta?.products || [],
      },
      scrape: {
        models_matched: raw.scrape?.models_matched ?? 0,
        models_in_catalog: inCatalog,
        models_with_prices: raw.scrape?.models_with_prices ?? withPrices,
        models_known_to_aws: raw.scrape?.models_known_to_aws ?? knownToAws,
        coverage_pct: raw.scrape?.coverage_pct ?? 0,
        price_coverage_pct:
          raw.scrape?.price_coverage_pct ??
          (inCatalog ? Math.round((100 * withPrices) / inCatalog) : 0),
        inventory_coverage_pct:
          raw.scrape?.inventory_coverage_pct ??
          (knownToAws
            ? Math.min(100, Math.round((100 * inCatalog) / knownToAws))
            : 100),
        warnings: raw.scrape?.warnings || [],
      },
      models,
    };
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
    modelHasPrice,
  };
})(window);
