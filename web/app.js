const state = {
  marketData: null,
  chatAvailable: false,
  stream: null,
  streamAvailable: false,
  agentExpanded: false,
};

const money = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function formatProviderLabel(provider) {
  const normalized = String(provider || "").trim().toLowerCase();
  if (normalized === "yfinance" || normalized === "yahoo" || normalized === "yahoo_finance") {
    return "Yahoo Finance";
  }
  if (normalized === "databento") {
    return "Databento";
  }
  if (normalized === "tradovate") {
    return "Tradovate";
  }
  if (normalized === "csv_file" || normalized === "csv_replay") {
    return "CSV replay";
  }
  return provider || "local backend";
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (!node) return;
  node.textContent = value ?? "-";
}

function setStatus(id, message, kind = "muted") {
  const node = document.getElementById(id);
  if (!node) return;
  node.className = `status-line ${kind}`;
  node.textContent = message;
}

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return money.format(value);
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function addChatMessage(role, text) {
  const container = document.getElementById("chatTranscript");
  const wrapper = document.createElement("article");
  const stamp = document.createElement("time");
  const body = document.createElement("p");

  wrapper.className = `chat-message ${role}`;
  stamp.textContent = role === "user" ? "You" : "Agent";
  body.textContent = text;
  wrapper.append(stamp, body);
  container.append(wrapper);
  container.scrollTop = container.scrollHeight;
}

function setAgentExpanded(expanded) {
  const widget = document.getElementById("agentWidget");
  const toggle = document.getElementById("agentToggle");
  const prompt = document.getElementById("chatPrompt");
  if (!widget || !toggle) return;

  state.agentExpanded = expanded;
  widget.classList.toggle("is-collapsed", !expanded);
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.setAttribute("aria-label", expanded ? "Collapse chat agent" : "Open chat agent");

  if (expanded && prompt) {
    requestAnimationFrame(() => prompt.focus());
  }
}

async function loadHealth() {
  const response = await fetch("/api/health");
  const payload = await response.json();
  state.chatAvailable = payload.agent_available;
  setText("chatAvailability", payload.agent_available ? "Available" : "Unavailable");
  const metadata = payload.display_metadata || {};
  const symbol = metadata.symbol || "NQ=F";
  const timeframeLabel = metadata.timeframe || "5 minutes";
  const chartType = metadata.chart_type || "Candles";
  const currency = metadata.currency || "USD";
  const tickSize = metadata.tick_size || "0.25";
  const pointValue = metadata.point_value || "20";
  const providerLabel = "Yahoo Finance via FibAgent MVP";
  state.streamAvailable = false;
  setText("instrumentTitle", `${symbol} shell with FibAgent MVP strategy output.`);
  setText("instrumentSubtitle", `The chart and setup analysis use Yahoo Finance bars through the deterministic MVP strategy. ${timeframeLabel} · ${chartType.toLowerCase()} · ${currency} · tick ${tickSize} · point value ${pointValue}`);
  setText("chartTitle", symbol);
  setText("chartHint", `${timeframeLabel} · ${chartType} · ${providerLabel}`);
  setText("analysisSource", providerLabel);
  if (!payload.agent_available && payload.agent_error) {
    setStatus("chatStatus", `Chat unavailable: ${payload.agent_error}`, "error");
  }
}

function applyMarketDataPayload(payload) {
  state.marketData = payload.rows;
  setText("rowsLoaded", String(payload.row_count));
  setText("latestTimestamp", payload.latest_timestamp.replace("T", " "));
  renderChart(payload.rows);
}

async function loadMarketData() {
  const response = await fetch("/api/mvp/analyze");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Market data request failed.");
  }
  applyMarketDataPayload(payload);
}

async function runAnalysis() {
  setStatus("analysisStatus", "Running analysis...");

  const params = new URLSearchParams({
    stop_buffer: document.getElementById("stopOffset").value,
    reward_multiple: document.getElementById("rewardMultiple").value,
  });

  const response = await fetch(`/api/mvp/analyze?${params.toString()}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Analysis failed.");
  }

  const result = payload.result;
  applyMarketDataPayload(payload);
  setText("analysisSource", `FibAgent MVP · ${payload.data_source}`);
  setText("setupDetected", result.setup_found ? "Found" : "No setup");
  setText("directionValue", result.direction || "neutral");
  setText("impulseType", String(result.confidence_score));
  setText("vwapAlignment", payload.data_source);
  setText("entryValue", formatValue(result.entry));
  setText("stopValue", formatValue(result.stop_loss));
  setText("targetValue", formatValue(result.take_profit));
  setText("riskRewardValue", "Explain only");
  setText("retraceZone", JSON.stringify(result.entry_zone, null, 2));
  setText("llmPayload", `${JSON.stringify(result, null, 2)}\n\n${payload.explanation}`);
  setStatus("analysisStatus", "MVP analysis refreshed.", "success");
}

async function sendChat(event) {
  event.preventDefault();
  setAgentExpanded(true);
  const textarea = document.getElementById("chatPrompt");
  const prompt = textarea.value.trim();

  if (!prompt) {
    return;
  }

  addChatMessage("user", prompt);
  textarea.value = "";
  setStatus("chatStatus", "Waiting for agent response...");

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  const payload = await response.json();

  if (!response.ok) {
    addChatMessage("assistant", payload.error || "Agent request failed.");
    setStatus("chatStatus", payload.details || payload.error || "Chat failed.", "error");
    return;
  }

  addChatMessage("assistant", payload.answer || "");
  setStatus("chatStatus", "Response received.", "success");
}

function renderChart(rows) {
  const container = document.getElementById("priceChart");
  if (!rows || !rows.length) {
    container.innerHTML = "";
    return;
  }

  const visibleRows = rows.slice(-36);
  const width = Math.max(640, container.clientWidth || 720);
  const height = 320;
  const paddingTop = 22;
  const paddingRight = 74;
  const paddingBottom = 28;
  const paddingLeft = 18;
  const priceAreaBottom = 220;
  const innerWidth = width - paddingLeft - paddingRight;
  const priceAreaHeight = priceAreaBottom - paddingTop;
  const highs = visibleRows.map((row) => row.high);
  const lows = visibleRows.map((row) => row.low);
  const volumes = visibleRows.map((row) => row.volume);
  const minPrice = Math.min(...lows);
  const maxPrice = Math.max(...highs);
  const maxVolume = Math.max(...volumes) || 1;
  const rawPriceRange = maxPrice - minPrice || 1;
  const paddedRange = rawPriceRange * 0.16;
  const chartMin = minPrice - paddedRange;
  const chartMax = maxPrice + paddedRange;
  const priceRange = chartMax - chartMin || 1;
  const candleSlotWidth = innerWidth / visibleRows.length;
  const candleBodyWidth = Math.max(5, Math.min(12, candleSlotWidth * 0.56));
  const volumeWidth = Math.max(4, candleSlotWidth * 0.72);

  const priceToY = (value) =>
    paddingTop + ((chartMax - value) / priceRange) * priceAreaHeight;

  let svg = `<svg viewBox="0 0 ${width} ${height}" class="fallback-chart-svg" role="img" aria-label="Local candlestick chart">`;
  [0.25, 0.5, 0.75].forEach((fraction) => {
    const y = paddingTop + priceAreaHeight * fraction;
    svg += `<line x1="${paddingLeft}" x2="${width - paddingRight}" y1="${y}" y2="${y}" stroke="rgba(173,211,229,0.12)" stroke-dasharray="6 10" />`;
  });

  visibleRows.forEach((row, index) => {
    const centerX = paddingLeft + index * candleSlotWidth + candleSlotWidth / 2;
    const isUp = row.close >= row.open;
    const wickColor = isUp ? "#59d7bd" : "#747980";
    const bodyFill = isUp ? "rgba(89,215,189,0.18)" : "rgba(116,121,128,0.24)";
    const openY = priceToY(row.open);
    const closeY = priceToY(row.close);
    const highY = priceToY(row.high);
    const lowY = priceToY(row.low);
    const bodyY = Math.min(openY, closeY);
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
    const barHeight = (row.volume / maxVolume) * 64;

    svg += `<line x1="${centerX}" x2="${centerX}" y1="${highY}" y2="${lowY}" stroke="${wickColor}" stroke-width="1.2" />`;
    svg += `<rect x="${centerX - candleBodyWidth / 2}" y="${bodyY}" width="${candleBodyWidth}" height="${bodyHeight}" rx="1.5" fill="${bodyFill}" stroke="${wickColor}" stroke-width="1.1" />`;
    svg += `<rect x="${centerX - volumeWidth / 2}" y="${height - paddingBottom - barHeight}" width="${volumeWidth}" height="${barHeight}" fill="${isUp ? "rgba(89,215,189,0.32)" : "rgba(116,121,128,0.4)"}" />`;
  });

  const latest = visibleRows[visibleRows.length - 1];
  const closeLineY = priceToY(latest.close);
  svg += `<line x1="${paddingLeft}" x2="${width - paddingRight}" y1="${closeLineY}" y2="${closeLineY}" stroke="${latest.close >= latest.open ? "rgba(89,215,189,0.34)" : "rgba(116,121,128,0.34)"}" stroke-dasharray="6 8" />`;

  [chartMax, (chartMax + chartMin) / 2, chartMin].forEach((level, index) => {
    const y = index === 0 ? paddingTop + 4 : index === 1 ? paddingTop + priceAreaHeight / 2 + 4 : paddingTop + priceAreaHeight + 4;
    svg += `<text x="${width - paddingRight + 8}" y="${y}" fill="#95a9b4" font-size="11">${money.format(level)}</text>`;
  });

  const labelStep = Math.max(1, Math.floor(visibleRows.length / 6));
  visibleRows.forEach((row, index) => {
    if (index % labelStep !== 0 && index !== visibleRows.length - 1) return;
    const timestamp = new Date(row.datetime);
    const label = timestamp.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: false });
    const x = paddingLeft + index * candleSlotWidth + candleSlotWidth / 2;
    svg += `<text x="${x}" y="${height - 6}" fill="#8ea1ad" font-size="11" text-anchor="middle">${label}</text>`;
  });

  visibleRows.forEach((row, index) => {
    const centerX = paddingLeft + index * candleSlotWidth + candleSlotWidth / 2;
    const tooltipWidth = 146;
    const tooltipHeight = 120;
    const tooltipX = Math.min(
      width - paddingRight - tooltipWidth - 4,
      Math.max(paddingLeft + 4, centerX - tooltipWidth / 2),
    );
    const tooltipY = centerX > width * 0.74 ? paddingTop + 8 : priceAreaBottom + 8;
    const timestamp = new Date(row.datetime);
    const timestampLabel = escapeHtml(
      timestamp.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }),
    );
    const directionClass = row.close >= row.open ? "up" : "down";

    svg += `<g class="candle-hover-group">`;
    svg += `<rect class="candle-hit-area" x="${paddingLeft + index * candleSlotWidth}" y="${paddingTop}" width="${candleSlotWidth}" height="${height - paddingBottom - paddingTop}" />`;
    svg += `<line class="candle-crosshair" x1="${centerX}" x2="${centerX}" y1="${paddingTop}" y2="${height - paddingBottom}" />`;
    svg += `<g class="candle-tooltip ${directionClass}" transform="translate(${tooltipX} ${tooltipY})">`;
    svg += `<rect width="${tooltipWidth}" height="${tooltipHeight}" rx="6" />`;
    svg += `<text x="10" y="18" class="tooltip-title">${timestampLabel}</text>`;
    svg += `<text x="10" y="40">O ${money.format(row.open)}</text>`;
    svg += `<text x="10" y="58">H ${money.format(row.high)}</text>`;
    svg += `<text x="10" y="76">L ${money.format(row.low)}</text>`;
    svg += `<text x="10" y="94">C ${money.format(row.close)}</text>`;
    svg += `<text x="10" y="112">V ${money.format(row.volume)}</text>`;
    svg += `</g></g>`;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  const previousClose = visibleRows.length > 1 ? visibleRows[visibleRows.length - 2].close : latest.open;
  const change = latest.close - previousClose;
  const changePct = previousClose ? (change / previousClose) * 100 : 0;
  setText(
    "chartStats",
    `O ${money.format(latest.open)}  H ${money.format(latest.high)}  L ${money.format(latest.low)}  C ${money.format(latest.close)}  ${change >= 0 ? "+" : ""}${money.format(change)} (${changePct.toFixed(2)}%)`,
  );
}

function connectStream() {
  if (!state.streamAvailable) {
    return;
  }

  if (state.stream) {
    state.stream.close();
  }

  const stream = new EventSource("/api/stream");
  stream.addEventListener("bars", (event) => {
    const payload = JSON.parse(event.data);
    applyMarketDataPayload(payload);
    setStatus("analysisStatus", "Local bars updating.", "success");
  });
  stream.onerror = () => {
    setStatus("analysisStatus", "Local stream disconnected. Using last known bars.", "error");
  };
  state.stream = stream;
}

async function bootstrap() {
  document.getElementById("agentToggle").addEventListener("click", () => {
    setAgentExpanded(!state.agentExpanded);
  });

  document.getElementById("agentClose").addEventListener("click", () => {
    setAgentExpanded(false);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.agentExpanded) {
      setAgentExpanded(false);
    }
  });

  document.getElementById("analysisForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await runAnalysis();
    } catch (error) {
      setStatus("analysisStatus", error.message, "error");
    }
  });

  document.getElementById("refreshAnalysis").addEventListener("click", async () => {
    try {
      await loadMarketData();
      await runAnalysis();
    } catch (error) {
      setStatus("analysisStatus", error.message, "error");
    }
  });

  const chatForm = document.getElementById("chatForm");
  const chatPrompt = document.getElementById("chatPrompt");
  chatForm.addEventListener("submit", sendChat);
  chatPrompt.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.requestSubmit();
    }
  });

  try {
    await Promise.all([loadHealth(), loadMarketData()]);
    connectStream();
    setStatus("analysisStatus", "Ready. Run analysis to check the current setup.");
    addChatMessage("assistant", "Ask about the latest bar, price move, or deterministic setup state.");
  } catch (error) {
    setStatus("analysisStatus", error.message, "error");
  }
}

bootstrap();
