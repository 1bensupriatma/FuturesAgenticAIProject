const money = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function setText(id, value) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = value ?? "-";
}

function setStatus(message, kind = "muted") {
  const node = document.getElementById("analysisStatus");
  node.className = `status-line ${kind}`;
  node.textContent = message;
}

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  return typeof value === "number" ? money.format(value) : String(value);
}

async function loadAnalysis() {
  setStatus("Running deterministic MVP analysis...");
  const response = await fetch("/api/analyze");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Analysis failed.");
  }

  const result = payload.result;
  setText("dataSource", payload.data_source);
  setText("rowsLoaded", String(payload.row_count));
  setText("latestTimestamp", payload.latest_timestamp);
  setText("setupFound", result.setup_found ? "Found" : "No setup");
  setText("directionValue", result.direction);
  setText("confidenceScore", String(result.confidence_score));
  setText("entryValue", formatValue(result.entry));
  setText("stopValue", formatValue(result.stop_loss));
  setText("targetValue", formatValue(result.take_profit));
  setText(
    "fibZoneValue",
    result.entry_zone
      ? `${money.format(result.entry_zone.fib_50)} / ${money.format(result.entry_zone.fib_618)}`
      : "-",
  );
  setText("strategyJson", JSON.stringify(result, null, 2));
  setText("explanationText", payload.explanation);
  renderChart(payload.rows);
  setStatus("MVP analysis complete.", "success");
}

function renderChart(rows) {
  const container = document.getElementById("priceChart");
  if (!rows || !rows.length) {
    container.innerHTML = "";
    return;
  }

  const width = Math.max(640, container.clientWidth || 720);
  const height = 320;
  const paddingTop = 22;
  const paddingRight = 74;
  const paddingBottom = 28;
  const paddingLeft = 18;
  const priceAreaBottom = 220;
  const innerWidth = width - paddingLeft - paddingRight;
  const priceAreaHeight = priceAreaBottom - paddingTop;
  const highs = rows.map((row) => row.high);
  const lows = rows.map((row) => row.low);
  const volumes = rows.map((row) => row.volume);
  const minPrice = Math.min(...lows);
  const maxPrice = Math.max(...highs);
  const maxVolume = Math.max(...volumes) || 1;
  const paddedRange = (maxPrice - minPrice || 1) * 0.18;
  const chartMin = minPrice - paddedRange;
  const chartMax = maxPrice + paddedRange;
  const priceRange = chartMax - chartMin || 1;
  const candleSlotWidth = innerWidth / rows.length;
  const candleBodyWidth = Math.max(14, Math.min(32, candleSlotWidth * 0.45));
  const volumeWidth = Math.max(10, candleSlotWidth * 0.48);

  const priceToY = (value) =>
    paddingTop + ((chartMax - value) / priceRange) * priceAreaHeight;

  let svg = `<svg viewBox="0 0 ${width} ${height}" class="fallback-chart-svg" role="img" aria-label="MVP candlestick chart">`;
  [0.25, 0.5, 0.75].forEach((fraction) => {
    const y = paddingTop + priceAreaHeight * fraction;
    svg += `<line x1="${paddingLeft}" x2="${width - paddingRight}" y1="${y}" y2="${y}" stroke="rgba(173,211,229,0.12)" stroke-dasharray="6 10" />`;
  });

  rows.forEach((row, index) => {
    const centerX = paddingLeft + index * candleSlotWidth + candleSlotWidth / 2;
    const isUp = row.close >= row.open;
    const wickColor = isUp ? "#59d7bd" : "#747980";
    const bodyFill = isUp ? "rgba(89,215,189,0.18)" : "rgba(116,121,128,0.24)";
    const openY = priceToY(row.open);
    const closeY = priceToY(row.close);
    const highY = priceToY(row.high);
    const lowY = priceToY(row.low);
    const bodyY = Math.min(openY, closeY);
    const bodyHeight = Math.max(2, Math.abs(closeY - openY));
    const barHeight = (row.volume / maxVolume) * 64;

    svg += `<line x1="${centerX}" x2="${centerX}" y1="${highY}" y2="${lowY}" stroke="${wickColor}" stroke-width="1.4" />`;
    svg += `<rect x="${centerX - candleBodyWidth / 2}" y="${bodyY}" width="${candleBodyWidth}" height="${bodyHeight}" rx="2" fill="${bodyFill}" stroke="${wickColor}" stroke-width="1.2" />`;
    svg += `<rect x="${centerX - volumeWidth / 2}" y="${height - paddingBottom - barHeight}" width="${volumeWidth}" height="${barHeight}" fill="${isUp ? "rgba(89,215,189,0.32)" : "rgba(116,121,128,0.4)"}" />`;
  });

  const latest = rows[rows.length - 1];
  const closeLineY = priceToY(latest.close);
  svg += `<line x1="${paddingLeft}" x2="${width - paddingRight}" y1="${closeLineY}" y2="${closeLineY}" stroke="rgba(89,215,189,0.34)" stroke-dasharray="6 8" />`;

  [chartMax, (chartMax + chartMin) / 2, chartMin].forEach((level, index) => {
    const y = index === 0 ? paddingTop + 4 : index === 1 ? paddingTop + priceAreaHeight / 2 + 4 : paddingTop + priceAreaHeight + 4;
    svg += `<text x="${width - paddingRight + 8}" y="${y}" fill="#95a9b4" font-size="11">${money.format(level)}</text>`;
  });

  rows.forEach((row, index) => {
    const x = paddingLeft + index * candleSlotWidth + candleSlotWidth / 2;
    const label = row.timestamp.slice(11, 16);
    svg += `<text x="${x}" y="${height - 6}" fill="#8ea1ad" font-size="11" text-anchor="middle">${label}</text>`;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  const previousClose = rows.length > 1 ? rows[rows.length - 2].close : latest.open;
  const change = latest.close - previousClose;
  const changePct = previousClose ? (change / previousClose) * 100 : 0;
  setText(
    "chartStats",
    `O ${money.format(latest.open)}  H ${money.format(latest.high)}  L ${money.format(latest.low)}  C ${money.format(latest.close)}  ${change >= 0 ? "+" : ""}${money.format(change)} (${changePct.toFixed(2)}%)`,
  );
}

async function bootstrap() {
  document.getElementById("runAnalysis").addEventListener("click", () => {
    loadAnalysis().catch((error) => setStatus(error.message, "error"));
  });
  document.getElementById("runPrimary").addEventListener("click", () => {
    loadAnalysis().catch((error) => setStatus(error.message, "error"));
  });

  try {
    const response = await fetch("/api/analyze");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load sample candles.");
    setText("dataSource", payload.data_source);
    setText("rowsLoaded", String(payload.row_count));
    setText("latestTimestamp", payload.latest_timestamp);
    renderChart(payload.rows);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

bootstrap();
