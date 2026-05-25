/**
 * @file Global constants and data path resolution.
 */
(function (global) {
  "use strict";

  const STALE_DAYS = 30;
  const PRICE_EPSILON = 1e-9;

  /**
   * Data directory for pricing.json / pricing.embed.js.
   * Set via <meta name="data-base"> (../data/ dev, data/ production deploy).
   */
  function getDataBase() {
    const meta = document.querySelector('meta[name="data-base"]');
    if (meta && meta.content) {
      const base = meta.content.trim();
      return base.endsWith("/") ? base : base + "/";
    }
    return "data/";
  }

  global.BedrockLens = global.BedrockLens || {};
  global.BedrockLens.CONSTANTS = {
    STALE_DAYS,
    PRICE_EPSILON,
    getDataBase,
    pricingJsonUrl: () => getDataBase() + "pricing.json",
    pricingEmbedUrl: () => getDataBase() + "pricing.embed.js",
  };
})(window);
