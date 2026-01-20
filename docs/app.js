// TradingView 스타일(유사) UI: Lightweight Charts
// 데이터: ../data/korea_premium.json

const $ = (id) => document.getElementById(id);

function toUnixDay(dateStr) {
  // "YYYY-MM-DD" -> UNIX time(초), UTC 기준 day start
  const [y, m, d] = dateStr.split("-").map(Number);
  return Math.floor(Date.UTC(y, m - 1, d) / 1000);
}

function formatKRW(n) {
  if (n === null || n === undefined) return "-";
  return Number(n).toLocaleString("ko-KR") + " KRW";
}

function mean(arr) {
  const xs = arr.filter(v => v !== null && v !== undefined);
  if (!xs.length) return null;
  return xs.reduce((a,b)=>a+b,0) / xs.length;
}

function movingAverage(points, windowSize) {
  // points: [{time, value}]
  const out = [];
  const values = points.map(p => p.value ?? null);
  for (let i = 0; i < points.length; i++) {
    let sum = 0, cnt = 0;
    for (let k = i - windowSize + 1; k <= i; k++) {
      if (k < 0) continue;
      const v = values[k];
      if (v === null || v === undefined) continue;
      sum += v; cnt++;
    }
    out.push({ time: points[i].time, value: cnt ? (sum / cnt) : null });
  }
  // lightweight-charts는 null 포인트는 그냥 건너뜀 -> 필터링
  return out.filter(p => p.value !== null && p.value !== undefined);
}

async function loadRows() {
  const res = await fetch("./data/korea_premium.json", { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load docs/data/korea_premium.json");
  return await res.json();
}


function listExchanges(rows) {
  const set = new Set();
  rows.forEach(r => Object.keys(r.premiums || {}).forEach(k => set.add(k)));
  return Array.from(set).sort();
}

function sliceByRange(rows, rangeValue) {
  if (rangeValue === "all") return rows;
  const days = Number(rangeValue);
  if (!Number.isFinite(days)) return rows;
  return rows.slice(Math.max(0, rows.length - days));
}

function buildLinePoints(rows, exchange) {
  // LightweightCharts LineSeries expects [{time, value}]
  const pts = [];
  for (const r of rows) {
    const v = r.premiums?.[exchange];
    if (v === null || v === undefined) continue; // 끊긴 구간은 건너뜀
    pts.push({ time: toUnixDay(r.date), value: Number(v) });
  }
  return pts;
}

function buildStats(rows, exchange) {
  const vals = rows.map(r => r.premiums?.[exchange]).filter(v => v !== null && v !== undefined).map(Number);
  const latestRow = [...rows].reverse().find(r => r.premiums?.[exchange] !== null && r.premiums?.[exchange] !== undefined);
  const prevRow = latestRow
    ? [...rows].reverse().find(r => r.date < latestRow.date && r.premiums?.[exchange] !== null && r.premiums?.[exchange] !== undefined)
    : null;

  const latest = latestRow ? Number(latestRow.premiums[exchange]) : null;
  const prev = prevRow ? Number(prevRow.premiums[exchange]) : null;
  const chg = (latest !== null && prev !== null) ? (latest - prev) : null;

  const avg = mean(vals);
  const min = vals.length ? Math.min(...vals) : null;
  const max = vals.length ? Math.max(...vals) : null;

  return { latest, prev, chg, avg, min, max, latestDate: latestRow?.date ?? null };
}

function renderStats(stats, exchange) {
  const el = $("stats");
  el.innerHTML = "";

  const mk = (label, value, extra = "") => {
    const div = document.createElement("div");
    div.className = "chip";
    div.innerHTML = `${label} <strong>${value}</strong> ${extra}`;
    return div;
  };

  el.appendChild(mk("거래소:", exchange));
  el.appendChild(mk("최신:", stats.latest !== null ? formatKRW(stats.latest) : "-",
    stats.latestDate ? `<span style="color:#90a0b3;">(${stats.latestDate})</span>` : ""));
  el.appendChild(mk("전일대비:", stats.chg !== null ? formatKRW(stats.chg) : "-"));
  el.appendChild(mk("평균:", stats.avg !== null ? formatKRW(Math.round(stats.avg)) : "-"));
  el.appendChild(mk("최저:", stats.min !== null ? formatKRW(stats.min) : "-"));
  el.appendChild(mk("최고:", stats.max !== null ? formatKRW(stats.max) : "-"));
}

function createChart(container) {
  const chart = LightweightCharts.createChart(container, {
    layout: {
      background: { color: "#0f1620" },
      textColor: "#d6dde6",
      fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, "Noto Sans KR", sans-serif',
    },
    grid: {
      vertLines: { color: "#1f2a37" },
      horzLines: { color: "#1f2a37" },
    },
    rightPriceScale: {
      borderColor: "#1f2a37",
    },
    timeScale: {
      borderColor: "#1f2a37",
      timeVisible: true,
      secondsVisible: false,
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    handleScroll: true,
    handleScale: true,
  });

  // responsive
  const ro = new ResizeObserver(() => {
    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
  });
  ro.observe(container);

  return chart;
}

let chart;
let lineSeries;
let ma7Series;
let ma30Series;
let maEnabled = true;

function setupSeries() {
  lineSeries = chart.addLineSeries({
    lineWidth: 2,
    priceLineVisible: true,
    lastValueVisible: true,
    crosshairMarkerVisible: true,
  });

  ma7Series = chart.addLineSeries({
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  });

  ma30Series = chart.addLineSeries({
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  });
}

function setMAVisible(visible) {
  maEnabled = visible;
  ma7Series.applyOptions({ visible });
  ma30Series.applyOptions({ visible });
  $("toggleMA").textContent = visible ? "MA(7/30) ON" : "MA(7/30) OFF";
}

async function main() {
  const rowsAll = await loadRows();
  const exchanges = listExchanges(rowsAll);

  const exSel = $("exchangeSelect");
  exchanges.forEach(ex => {
    const opt = document.createElement("option");
    opt.value = ex;
    opt.textContent = ex;
    exSel.appendChild(opt);
  });

  const container = $("chart");
  chart = createChart(container);
  setupSeries();

  function update() {
    const exchange = exSel.value;
    const range = $("rangeSelect").value;
    const rows = sliceByRange(rowsAll, range);

    const points = buildLinePoints(rows, exchange);
    lineSeries.setData(points);

    // MA 계산은 line points 기반 (null 제거된 상태)
    const ma7 = movingAverage(points, 7);
    const ma30 = movingAverage(points, 30);
    ma7Series.setData(ma7);
    ma30Series.setData(ma30);
    setMAVisible(maEnabled);

    // 화면 자동 맞추기
    chart.timeScale().fitContent();

    // 통계
    const stats = buildStats(rows, exchange);
    renderStats(stats, exchange);
  }

  // 기본값
  exSel.value = exchanges.includes("upbit") ? "upbit" : (exchanges[0] || "");
  $("rangeSelect").value = "180"; // 기본 6개월
  $("toggleMA").addEventListener("click", () => setMAVisible(!maEnabled));

  exSel.addEventListener("change", update);
  $("rangeSelect").addEventListener("change", update);

  update();
}

main().catch(err => {
  console.error(err);
  $("stats").innerHTML = `<div class="chip">에러: <strong>${String(err.message || err)}</strong></div>`;
});
