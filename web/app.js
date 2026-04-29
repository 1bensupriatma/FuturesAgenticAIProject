const state = {
  marketData: null,
  chatAvailable: false,
};

const money = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

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

function renderChart(rows) {
  const svg = document.getElementById("priceChart");
  svg.innerHTML = "";

  if (!rows || !rows.length) {
    return;
  }

  const width = 720;
  const height = 280;
  const padding = 28;
  const closes = rows.map((row) => row.close);
  const volumes = rows.map((row) => row.volume);
  const minPrice = Math.min(...closes);
  const maxPrice = Math.max(...closes);
  const maxVolume = Math.max(...volumes);
  const priceRange = maxPrice - minPrice || 1;

  const linePoints = rows
    .map((row, index) => {
      const x = padding + (index / (rows.length - 1 || 1)) * (width - padding * 2);
      const y = height - padding - ((row.close - minPrice) / priceRange) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  const volumeWidth = (width - padding * 2) / rows.length;
  rows.forEach((row, index) => {
    const x = padding + index * volumeWidth;
    const barHeight = maxVolume ? (row.volume / maxVolume) * 52 : 0;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", String(x));
    rect.setAttribute("y", String(height - padding - barHeight));
    rect.setAttribute("width", String(Math.max(2, volumeWidth - 2)));
    rect.setAttribute("height", String(barHeight));
    rect.setAttribute("fill", "rgba(102, 217, 184, 0.18)");
    svg.append(rect);
  });

  const path = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  path.setAttribute("points", linePoints);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#66d9b8");
  path.setAttribute("stroke-width", "3");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-linecap", "round");

  const baseline = document.createElementNS("http://www.w3.org/2000/svg", "line");
  baseline.setAttribute("x1", String(padding));
  baseline.setAttribute("x2", String(width - padding));
  baseline.setAttribute("y1", String(height - padding));
  baseline.setAttribute("y2", String(height - padding));
  baseline.setAttribute("stroke", "rgba(255,255,255,0.18)");

  const topLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  topLabel.setAttribute("x", String(padding));
  topLabel.setAttribute("y", "18");
  topLabel.setAttribute("fill", "#95a9b4");
  topLabel.setAttribute("font-size", "12");
  topLabel.textContent = `High ${money.format(maxPrice)}`;

  const bottomLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  bottomLabel.setAttribute("x", String(padding));
  bottomLabel.setAttribute("y", String(height - 8));
  bottomLabel.setAttribute("fill", "#95a9b4");
  bottomLabel.setAttribute("font-size", "12");
  bottomLabel.textContent = `Low ${money.format(minPrice)}`;

  svg.append(baseline, path, topLabel, bottomLabel);
}

async function loadHealth() {
  const response = await fetch("/api/health");
  const payload = await response.json();
  state.chatAvailable = payload.agent_available;
  setText("chatAvailability", payload.agent_available ? "Available" : "Unavailable");
  if (!payload.agent_available && payload.agent_error) {
    setStatus("chatStatus", `Chat unavailable: ${payload.agent_error}`, "error");
  }
}

async function loadMarketData() {
  const response = await fetch("/api/market-data");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Market data request failed.");
  }
  state.marketData = payload.rows;
  setText("rowsLoaded", String(payload.row_count));
  setText("latestTimestamp", payload.latest_timestamp.replace("T", " "));
  renderChart(payload.rows);
}

async function runAnalysis() {
  setStatus("analysisStatus", "Running analysis...");

  const params = new URLSearchParams({
    stop_offset: document.getElementById("stopOffset").value,
    reward_multiple: document.getElementById("rewardMultiple").value,
    use_vwap_filter: String(document.getElementById("useVwapFilter").checked),
  });

  const response = await fetch(`/api/analyze?${params.toString()}`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Analysis failed.");
  }

  const setup = payload.latest_setup;
  setText("setupDetected", setup.setup_detected ? "Detected" : "No setup");
  setText("directionValue", setup.direction || "None");
  setText("impulseType", setup.impulse_type || "None");
  setText("vwapAlignment", setup.vwap_alignment === null ? "N/A" : String(setup.vwap_alignment));
  setText("entryValue", formatValue(setup.entry));
  setText("stopValue", formatValue(setup.stop));
  setText("targetValue", formatValue(setup.target));
  setText("riskRewardValue", formatValue(setup.risk_reward));
  setText("retraceZone", JSON.stringify(setup.retrace_zone, null, 2));
  setText("llmPayload", JSON.stringify(payload.llm_payload, null, 2));
  setStatus("analysisStatus", "Analysis refreshed.", "success");
}

async function sendChat(event) {
  event.preventDefault();
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

async function bootstrap() {
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

  document.getElementById("chatForm").addEventListener("submit", sendChat);

  try {
    await Promise.all([loadHealth(), loadMarketData(), runAnalysis()]);
    addChatMessage("assistant", "Ask about the latest bar, price move, or deterministic setup state.");
  } catch (error) {
    setStatus("analysisStatus", error.message, "error");
  }
}

bootstrap();
