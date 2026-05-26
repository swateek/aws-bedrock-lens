/**
 * @file Shared formatting and DOM helpers.
 */
(function (global) {
  "use strict";

  const { PRICE_EPSILON } = global.BedrockLens.CONSTANTS;

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

  function modelHasPrice(model) {
    const od = model.on_demand || {};
    return [
      "input_per_1m",
      "output_per_1m",
      "standard_per_image",
      "premium_per_image",
    ].some((k) => od[k] != null && Number.isFinite(od[k]));
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
    resolveAssetUrl,
    pinFavicon,
  };
})(window);
