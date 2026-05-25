/**
 * @file Comparison table rendering and row logic.
 */
(function (global) {
  "use strict";

  const { escapeHtml, formatPrice, formatContext, minFinite, isCheapest } =
    global.BedrockLens.util;

  function formatListPrice(model) {
    const od = model.on_demand || {};
    if (model.pricing_type === "image") {
      const parts = [];
      if (od.standard_per_image != null) {
        parts.push(`${formatPrice(od.standard_per_image)}/img std`);
      }
      if (od.premium_per_image != null) {
        parts.push(`${formatPrice(od.premium_per_image)}/img prem`);
      }
      return parts.length ? parts.join(" · ") : "—";
    }
    if (model.pricing_type === "embedding") {
      return `${formatPrice(od.input_per_1k)} / 1K in · embedding`;
    }
    return `${formatPrice(od.input_per_1k)} / ${formatPrice(od.output_per_1k)} · ${formatContext(model.context_window)} · ${(model.modalities || []).join(", ") || "—"}`;
  }

  function homogeneousType(models) {
    const types = new Set(models.map((m) => m.pricing_type));
    if (types.size === 1) return [...types][0];
    return "mixed";
  }

  function getCompareRows(models) {
    const rows = [
      { label: "Provider", render: (m) => m.provider },
      {
        label: "Source",
        render: (m) => (m.pricing_source === "auto" ? "auto" : "manual"),
      },
      {
        label: "Model ID",
        render: (m) => escapeHtml(m.model_id),
        html: true,
      },
    ];

    const kind = homogeneousType(models);

    if (kind === "token" || kind === "embedding") {
      const minIn = minFinite(models.map((m) => m.on_demand?.input_per_1k));
      rows.push({
        label: "Input / 1K",
        render: (m) => formatPrice(m.on_demand?.input_per_1k),
        best: (m) => isCheapest(m.on_demand?.input_per_1k, minIn),
      });

      const hasOutput = models.some(
        (m) => m.pricing_type === "token" && m.on_demand?.output_per_1k != null
      );
      if (hasOutput) {
        const minOut = minFinite(
          models
            .filter((m) => m.pricing_type === "token")
            .map((m) => m.on_demand?.output_per_1k)
        );
        rows.push({
          label: "Output / 1K",
          render: (m) =>
            m.pricing_type === "embedding"
              ? "—"
              : formatPrice(m.on_demand?.output_per_1k),
          best: (m) =>
            m.pricing_type === "token" &&
            isCheapest(m.on_demand?.output_per_1k, minOut),
        });
      }
    } else if (kind === "image") {
      const minStd = minFinite(models.map((m) => m.on_demand?.standard_per_image));
      rows.push({
        label: "Standard / image",
        render: (m) => formatPrice(m.on_demand?.standard_per_image),
        best: (m) => isCheapest(m.on_demand?.standard_per_image, minStd),
      });
      if (models.some((m) => m.on_demand?.premium_per_image != null)) {
        const minPrem = minFinite(
          models.map((m) => m.on_demand?.premium_per_image)
        );
        rows.push({
          label: "Premium / image",
          render: (m) => formatPrice(m.on_demand?.premium_per_image),
          best: (m) => isCheapest(m.on_demand?.premium_per_image, minPrem),
        });
      }
    } else {
      rows.push({
        label: "Pricing",
        render: (m) => escapeHtml(formatListPrice(m)),
        html: true,
      });
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
        label: "Regions",
        render: (m) => {
          const n = (m.regions || []).length;
          return n === 1 ? "1 region" : `${n} regions`;
        },
      }
    );

    if (models.length >= 2) {
      const shared = models
        .map((m) => new Set(m.regions || []))
        .reduce((acc, set) => new Set([...acc].filter((r) => set.has(r))));
      rows.push({
        label: "Shared regions",
        render: () =>
          escapeHtml([...shared].sort().join(", ") || "—"),
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
