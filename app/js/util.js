/**
 * @file Shared formatting, pricing resolution, and DOM helpers.
 */
(function (global) {
  "use strict";

  const { PRICE_EPSILON } = global.BedrockLens.CONSTANTS;

  const TIER_LABELS = {
    on_demand: "on-demand",
    on_demand_global: "on-demand global",
    batch: "batch",
    batch_global: "batch global",
    flex: "flex",
    priority: "priority",
    cache: "cache",
    cache_global: "cache global",
  };

  const PRICE_FIELDS = [
    "input_per_1m",
    "output_per_1m",
    "standard_per_image",
    "premium_per_image",
    "per_second",
    "per_search_unit",
    "read_input_per_1m",
    "write_input_per_1m",
    "write_1h_input_per_1m",
  ];

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str).replace(/'/g, "&#39;");
  }

  function formatPrice(value, unknownLabel) {
    if (value === null || value === undefined) {
      return unknownLabel === undefined ? "—" : unknownLabel;
    }
    if (value >= 1) return `$${value.toFixed(2)}`;
    if (value >= 0.01) return `$${value.toFixed(3)}`;
    if (value >= 0.001) return `$${value.toFixed(4)}`;
    return `$${value.toFixed(5)}`;
  }

  function formatContext(ctx) {
    if (ctx == null) return "—";
    if (ctx >= 1000) return `${Math.round(ctx / 1000)}K ctx`;
    return `${ctx} ctx`;
  }

  function daysSince(isoDate) {
    if (!isoDate) return null;
    const then = new Date(isoDate + "T00:00:00");
    const now = new Date();
    return Math.floor((now - then) / (1000 * 60 * 60 * 24));
  }

  function formatRelativeDate(isoDate) {
    const days = daysSince(isoDate);
    if (days === null) return "unknown";
    if (days < 0) return "in the future";
    if (days === 0) return "today";
    if (days === 1) return "1 day ago";
    return `${days} days ago`;
  }

  function pricesEqual(a, b) {
    if (a == null && b == null) return true;
    if (a == null || b == null) return false;
    return Math.abs(a - b) < PRICE_EPSILON;
  }

  function minFinite(values) {
    const nums = values.filter((v) => v != null && Number.isFinite(v));
    if (nums.length === 0) return null;
    return Math.min(...nums);
  }

  function isCheapest(value, min) {
    return min != null && value != null && pricesEqual(value, min);
  }

  function sliceHasPrice(slice) {
    if (!slice) return false;
    return PRICE_FIELDS.some(
      (k) => slice[k] != null && Number.isFinite(slice[k]),
    );
  }

  function modelHasPrice(model, region, tier) {
    if (region || tier) {
      return sliceHasPrice(resolveRates(model, region, tier));
    }
    if (sliceHasPrice(model.on_demand)) return true;
    const lp = model.list_prices || {};
    return Object.values(lp).some((tiers) =>
      Object.values(tiers || {}).some(sliceHasPrice),
    );
  }

  function resolveRates(model, region, tier) {
    const catalogDefault = model._defaultPriceRegion || "us-east-1";
    // Prefer explicitly selected availability region; else catalog default
    const r = region || catalogDefault;
    const t = tier || "on_demand";
    const listPrices = model.list_prices || {};
    const regionPrices = listPrices[r] || {};
    if (regionPrices[t] && sliceHasPrice(regionPrices[t])) {
      return { ...regionPrices[t] };
    }
    // Non-default tiers must exist explicitly — do not silently use on_demand
    if (t !== "on_demand") {
      return {};
    }
    if (regionPrices.on_demand && sliceHasPrice(regionPrices.on_demand)) {
      return { ...regionPrices.on_demand };
    }
    // Only fall back to catalog default when browsing "All" regions
    if (!region || region === catalogDefault) {
      const fallback = listPrices[catalogDefault]?.on_demand;
      if (fallback && sliceHasPrice(fallback)) return { ...fallback };
      return { ...(model.on_demand || {}) };
    }
    // Selected region has no published list price for this tier
    return {};
  }

  function pricedRegionsForModel(model) {
    const lp = model.list_prices || {};
    return Object.keys(lp)
      .filter((r) => Object.values(lp[r] || {}).some(sliceHasPrice))
      .sort();
  }

  function tiersForModel(model, region) {
    const r = region || "us-east-1";
    const tiers = model.list_prices?.[r] || {};
    return Object.keys(tiers)
      .filter((t) => sliceHasPrice(tiers[t]))
      .sort();
  }

  function formatTierLabel(tier) {
    return TIER_LABELS[tier] || tier;
  }

  function formatScopeChip(region, tier) {
    return `${region || "us-east-1"} · ${formatTierLabel(tier || "on_demand")}`;
  }

  function unknownPriceReason(model, region, tier) {
    if (model.availability === "preview") {
      return "Preview — no public list price";
    }
    if (
      model.notes &&
      /no public|unpriced|price unknown|not available/i.test(model.notes)
    ) {
      return model.notes.length > 80 ? "No public list price" : model.notes;
    }
    if (region || tier) {
      return "No public list price for this region/tier";
    }
    return "No public on-demand list price";
  }

  function blendedCost(rates, inWeight, outWeight) {
    const inn = rates?.input_per_1m;
    const out = rates?.output_per_1m;
    if (inn == null || out == null) return null;
    const total = inWeight + outWeight;
    if (total <= 0) return null;
    return (inn * inWeight + out * outWeight) / total;
  }

  function getTheme() {
    return document.documentElement.getAttribute("data-theme") || "";
  }

  function effectiveTheme() {
    const explicit = getTheme();
    if (explicit === "light" || explicit === "dark") return explicit;
    const prefersDark =
      global.matchMedia &&
      global.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  }

  function themeToggleLabel(theme) {
    const current = theme || effectiveTheme();
    return current === "dark" ? "Light Mode" : "Dark Mode";
  }

  function updateThemeToggle(button) {
    if (!button) return;
    const label = themeToggleLabel();
    button.textContent = label;
    button.setAttribute(
      "aria-label",
      label === "Dark Mode" ? "Switch to dark mode" : "Switch to light mode",
    );
  }

  function applyTheme(theme) {
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
      try {
        localStorage.setItem("bedrock-lens-theme", theme);
      } catch {
        /* ignore */
      }
    } else {
      document.documentElement.removeAttribute("data-theme");
      try {
        localStorage.removeItem("bedrock-lens-theme");
      } catch {
        /* ignore */
      }
    }
  }

  function initTheme() {
    let stored = null;
    try {
      stored = localStorage.getItem("bedrock-lens-theme");
    } catch {
      stored = null;
    }
    if (stored === "light" || stored === "dark") {
      applyTheme(stored);
      return stored;
    }
    // Follow system preference via CSS; leave data-theme unset
    return "";
  }

  function cycleTheme() {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    return next;
  }

  /** Directory containing index.html (handles /app vs /app/ and GH Pages subpaths). */
  function assetDirFromPath(pathname) {
    if (pathname.endsWith("/")) return pathname;
    if (/\.html$/i.test(pathname)) {
      const slash = pathname.lastIndexOf("/");
      return slash >= 0 ? pathname.slice(0, slash + 1) : "/";
    }
    return `${pathname}/`;
  }

  function resolveAssetUrl(filename) {
    const dir = assetDirFromPath(global.location.pathname);
    return new URL(filename, `${global.location.origin}${dir}`).href;
  }

  function trackEvent(name, params) {
    if (typeof gtag === "function" && global.GA_MEASUREMENT_ID) {
      gtag("event", name, params);
    }
  }

  /** Keep favicon href absolute so Chrome does not 404 it after replaceState / view changes. */
  function pinFavicon() {
    const link = document.querySelector('link[rel="icon"]');
    if (!link) return;
    const url = resolveAssetUrl("favicon.ico");
    if (link.href !== url) link.href = url;
  }

  global.BedrockLens.util = {
    escapeHtml,
    escapeAttr,
    formatPrice,
    formatContext,
    daysSince,
    formatRelativeDate,
    pricesEqual,
    minFinite,
    isCheapest,
    modelHasPrice,
    resolveRates,
    sliceHasPrice,
    pricedRegionsForModel,
    tiersForModel,
    formatTierLabel,
    formatScopeChip,
    unknownPriceReason,
    blendedCost,
    initTheme,
    applyTheme,
    cycleTheme,
    getTheme,
    effectiveTheme,
    themeToggleLabel,
    updateThemeToggle,
    resolveAssetUrl,
    pinFavicon,
    trackEvent,
    TIER_LABELS,
  };
})(window);
