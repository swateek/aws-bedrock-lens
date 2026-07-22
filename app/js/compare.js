/**
 * @file Comparison table rendering and row logic.
 */
(function (global) {
  "use strict";

  const {
    escapeHtml,
    formatPrice,
    formatContext,
    minFinite,
    isCheapest,
    resolveRates,
    formatScopeChip,
    unknownPriceReason,
    blendedCost,
    sliceHasPrice,
  } = global.BedrockLens.util;

  function scope() {
    return (
      global.BedrockLens._priceScope || {
        region: "us-east-1",
        tier: "on_demand",
        blendIn: 1,
        blendOut: 3,
      }
    );
  }

  function ratesFor(model) {
    const s = scope();
    return resolveRates(model, s.region, s.tier);
  }

  function formatListPrice(model, opts) {
    const s = scope();
    const region = opts?.region ?? s.region;
    const tier = opts?.tier ?? s.tier;
    const od = resolveRates(model, region, tier);
    if (!sliceHasPrice(od)) {
      return unknownPriceReason(model, region, tier);
    }
    if (model.pricing_type === "image") {
      const parts = [];
      if (od.standard_per_image != null) {
        parts.push(`${formatPrice(od.standard_per_image)} / image (standard)`);
      }
      if (od.premium_per_image != null) {
        parts.push(`${formatPrice(od.premium_per_image)} / image (premium)`);
      }
      return parts.length ? parts.join(" · ") : "—";
    }
    if (model.pricing_type === "embedding") {
      return `${formatPrice(od.input_per_1m)} / 1M input · embedding`;
    }
    if (model.pricing_type === "video") {
      return `${formatPrice(od.per_second)} / sec · video`;
    }
    if (model.pricing_type === "rerank") {
      return `${formatPrice(od.per_search_unit)} / search · rerank`;
    }
    return `${formatPrice(od.input_per_1m)} / 1M in · ${formatPrice(od.output_per_1m)} / 1M out · ${formatContext(model.context_window)}`;
  }

  function homogeneousType(models) {
    const types = new Set(models.map((m) => m.pricing_type));
    if (types.size === 1) return [...types][0];
    return "mixed";
  }

  function pushMetricRow(rows, label, models, getter) {
    const values = models.map(getter);
    const withVal = values.filter((v) => v != null && Number.isFinite(v));
    if (withVal.length < 1) return;
    const min = minFinite(values);
    rows.push({
      label,
      render: (m) => {
        const v = getter(m);
        return v == null ? "—" : formatPrice(v, unknownPriceReason(m));
      },
      best: (m) => isCheapest(getter(m), min),
    });
  }

  function getCompareRows(models) {
    const s = scope();
    const rows = [
      { label: "Provider", render: (m) => m.provider },
      {
        label: "Source",
        render: (m) =>
          m.pricing_source === "price_list" || m.pricing_source === "auto"
            ? "price_list"
            : "manual",
      },
      {
        label: "Pricing scope",
        render: () => formatScopeChip(s.region, s.tier),
      },
      {
        label: "Model ID",
        render: (m) => escapeHtml(m.model_id),
        html: true,
      },
    ];

    const kind = homogeneousType(models);

    if (kind === "token" || kind === "embedding") {
      pushMetricRow(
        rows,
        "Input / 1M",
        models,
        (m) => ratesFor(m).input_per_1m,
      );

      const hasOutput = models.some(
        (m) => m.pricing_type === "token" && ratesFor(m).output_per_1m != null,
      );
      if (hasOutput) {
        pushMetricRow(rows, "Output / 1M", models, (m) =>
          m.pricing_type === "embedding" ? null : ratesFor(m).output_per_1m,
        );
      }

      if (kind === "token") {
        const blends = models.map((m) =>
          blendedCost(ratesFor(m), s.blendIn, s.blendOut),
        );
        if (blends.some((v) => v != null)) {
          const minBlend = minFinite(blends);
          rows.push({
            label: `Blended / 1M (${s.blendIn}:${s.blendOut})`,
            render: (m) => {
              const v = blendedCost(ratesFor(m), s.blendIn, s.blendOut);
              return v == null ? "—" : formatPrice(v);
            },
            best: (m) =>
              isCheapest(
                blendedCost(ratesFor(m), s.blendIn, s.blendOut),
                minBlend,
              ),
          });
        }
      }

      // Cache rows when present on any model for this region
      pushMetricRow(rows, "Cache read / 1M", models, (m) => {
        const cache = resolveRates(m, s.region, "cache");
        return cache.read_input_per_1m;
      });
      pushMetricRow(rows, "Cache write / 1M", models, (m) => {
        const cache = resolveRates(m, s.region, "cache");
        return cache.write_input_per_1m;
      });
      pushMetricRow(rows, "Cache write 1h / 1M", models, (m) => {
        const cache = resolveRates(m, s.region, "cache");
        return cache.write_1h_input_per_1m;
      });
    } else if (kind === "image") {
      pushMetricRow(
        rows,
        "Standard / image",
        models,
        (m) => ratesFor(m).standard_per_image,
      );
      pushMetricRow(
        rows,
        "Premium / image",
        models,
        (m) => ratesFor(m).premium_per_image,
      );
    } else if (kind === "video") {
      pushMetricRow(
        rows,
        "Price / second",
        models,
        (m) => ratesFor(m).per_second,
      );
    } else if (kind === "rerank") {
      pushMetricRow(
        rows,
        "Price / search unit",
        models,
        (m) => ratesFor(m).per_search_unit,
      );
    } else {
      // Mixed: summary + shared numeric metrics
      rows.push({
        label: "Summary",
        render: (m) => escapeHtml(formatListPrice(m)),
        html: true,
      });
      pushMetricRow(
        rows,
        "Input / 1M",
        models,
        (m) => ratesFor(m).input_per_1m,
      );
      pushMetricRow(
        rows,
        "Output / 1M",
        models,
        (m) => ratesFor(m).output_per_1m,
      );
      pushMetricRow(
        rows,
        "Standard / image",
        models,
        (m) => ratesFor(m).standard_per_image,
      );
      pushMetricRow(
        rows,
        "Premium / image",
        models,
        (m) => ratesFor(m).premium_per_image,
      );
      pushMetricRow(
        rows,
        "Price / second",
        models,
        (m) => ratesFor(m).per_second,
      );
      pushMetricRow(
        rows,
        "Price / search unit",
        models,
        (m) => ratesFor(m).per_search_unit,
      );
    }

    rows.push(
      {
        label: "Context window",
        render: (m) =>
          m.context_window != null ? m.context_window.toLocaleString() : "—",
      },
      {
        label: "Modalities",
        render: (m) => (m.modalities || []).join(", ") || "—",
      },
      {
        label: "Available regions",
        render: (m) => {
          const list = escapeHtml(
            (m.regions || []).slice().sort().join(", ") || "—",
          );
          return `<span class="region-list">${list}</span>`;
        },
        html: true,
      },
    );

    if (models.length >= 2) {
      const shared = models
        .map((m) => new Set(m.regions || []))
        .reduce((acc, set) => new Set([...acc].filter((r) => set.has(r))));
      rows.push({
        label: "Shared regions",
        render: () => escapeHtml([...shared].sort().join(", ") || "—"),
        html: true,
        fullWidth: true,
      });
    }

    return rows;
  }

  function renderCompareTable(models, thead, tbody) {
    if (models.length === 0) return;

    const headerRow = document.createElement("tr");
    headerRow.innerHTML = '<th scope="col"></th>';
    for (const m of models) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = m.display_name;
      headerRow.appendChild(th);
    }
    thead.innerHTML = "";
    thead.appendChild(headerRow);

    const rows = getCompareRows(models);
    tbody.innerHTML = "";

    for (const row of rows) {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.scope = "row";
      th.textContent = row.label;
      tr.appendChild(th);

      if (row.fullWidth) {
        const td = document.createElement("td");
        td.colSpan = models.length;
        const content = row.render(models[0]);
        td.innerHTML = `<span class="shared-regions">${content}</span>`;
        tr.appendChild(td);
      } else {
        for (const m of models) {
          const td = document.createElement("td");
          const content = row.render(m);
          const best = row.best && row.best(m);
          if (row.html) {
            td.innerHTML = best
              ? `<span class="price price--best">${content}</span><span class="check" aria-hidden="true">✓</span>`
              : content;
          } else {
            td.innerHTML = best
              ? `<span class="price price--best">${escapeHtml(content)}</span><span class="check" aria-hidden="true">✓</span>`
              : `<span class="price">${escapeHtml(content)}</span>`;
          }
          tr.appendChild(td);
        }
      }
      tbody.appendChild(tr);
    }
  }

  global.BedrockLens.compare = {
    formatListPrice,
    getCompareRows,
    renderCompareTable,
  };
})(window);
