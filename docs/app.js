async function loadData() {
  const res = await fetch("../data/korea_premium.json", { cache: "no-store" });
  return await res.json();
}

function pickExchanges(rows) {
  const set = new Set();
  for (const r of rows) {
    for (const k of Object.keys(r.premiums || {})) set.add(k);
  }
  return Array.from(set).sort();
}

function buildSeries(rows, exchange) {
  const labels = rows.map(r => r.date);
  const values = rows.map(r => {
    const v = r.premiums?.[exchange];
    return (v === null || v === undefined) ? null : v;
  });
  return { labels, values };
}

let chart;

function renderChart(labels, values, exchange) {
  const ctx = document.getElementById("chart");
  if (chart) chart.destroy();

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: `${exchange} 프리미엄(KRW)`,
        data: values,
        spanGaps: true,
        pointRadius: 0,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.parsed.y;
              if (v === null) return "값 없음";
              return ` ${v.toLocaleString()} KRW`;
            }
          }
        }
      },
      scales: {
        y: {
          ticks: {
            callback: (v) => Number(v).toLocaleString()
          }
        }
      }
    }
  });
}

(async function main() {
  const rows = await loadData();
  const exchanges = pickExchanges(rows);

  const sel = document.getElementById("exchangeSelect");
  for (const ex of exchanges) {
    const opt = document.createElement("option");
    opt.value = ex;
    opt.textContent = ex;
    sel.appendChild(opt);
  }

  function update() {
    const ex = sel.value;
    const { labels, values } = buildSeries(rows, ex);

    const lastIdx = values.map((v, i) => [v, i]).filter(([v]) => v !== null).slice(-1)[0];
    const latest = lastIdx ? `${labels[lastIdx[1]]} : ${lastIdx[0].toLocaleString()} KRW` : "최신 값 없음";
    document.getElementById("latest").textContent = `최신: ${latest}`;

    renderChart(labels, values, ex);
  }

  sel.value = exchanges[0] || "";
  sel.addEventListener("change", update);
  update();
})();
