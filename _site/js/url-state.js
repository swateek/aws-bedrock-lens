/**
 * @file URL query sync for selected model IDs.
 */
(function (global) {
  "use strict";

  function parseSelection(search, validIds) {
    const raw = new URLSearchParams(search).get("models");
    if (!raw) return new Set();
    const selected = new Set();
    for (const id of raw.split(",")) {
      const trimmed = id.trim();
      if (trimmed && validIds.has(trimmed)) selected.add(trimmed);
    }
    return selected;
  }

  function syncToUrl(selected) {
    const params = new URLSearchParams(global.location.search);
    if (selected.size > 0) {
      params.set("models", [...selected].join(","));
    } else {
      params.delete("models");
    }
    const qs = params.toString();
    const url = qs
      ? `${global.location.pathname}?${qs}`
      : global.location.pathname;
    global.history.replaceState(null, "", url);
  }

  global.BedrockLens.urlState = {
    parseSelection,
    syncToUrl,
  };
})(window);
