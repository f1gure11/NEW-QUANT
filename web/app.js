const inputs = [
  "instId",
  "lower",
  "upper",
  "leverage",
  "gridBps",
  "minNetBps",
  "softBps",
  "hardBps",
  "mode",
  "adaptiveWidthBps",
  "adaptiveMinWidthBps",
  "adaptiveMaxWidthBps",
  "adaptiveVolMultiplier",
  "rangeDriftMode",
  "rangeDriftWeightBps",
  "rangeDriftMaxBps",
];
const consolePathPrefix = window.location.pathname.startsWith("/console") ? "/console" : "";
const apiBasePath = `${consolePathPrefix}/api`;
const storageKey = "okxQuantConsole.params.v1";
const persistedOnlyInputs = [
  "missedTpOrdType",
  "missedTpSlippageBps",
  "portfolioTradingMode",
  "portfolioMarketRegimeFilter",
  "portfolioMarketRegimeMinConfidence",
  "portfolioMarketRegimeMixedPolicy",
];
const persistedCheckboxes = [
  "autoRefresh",
];
const persistedControls = [...new Set([...inputs, ...persistedOnlyInputs, ...persistedCheckboxes])];
const ethDefaults = {
  instId: "ETH-USDT-SWAP",
  lower: "1500",
  upper: "1800",
  leverage: "7",
  gridBps: "10",
  minNetBps: "1",
  softBps: "35",
  hardBps: "60",
  mode: "adaptive",
  adaptiveWidthBps: "420",
  adaptiveMinWidthBps: "260",
  adaptiveMaxWidthBps: "1200",
  adaptiveVolMultiplier: "12",
  rangeDriftMode: "cooldown",
  rangeDriftWeightBps: "2500",
  rangeDriftMaxBps: "250",
};
let autoTimer = null;
let latestData = null;
let latestPortfolio = null;

function apiUrl(path) {
  return `${apiBasePath}${path.startsWith("/") ? path : `/${path}`}`;
}
let refreshInFlight = false;

window.addEventListener("DOMContentLoaded", () => {
  try {
    restoreSavedParams();
    document.getElementById("refreshBtn").addEventListener("click", refresh);
    document.getElementById("instId").addEventListener("change", () => {
      syncMonitorFromBotForm(selectedBotKey());
      saveParams();
    });
    document.getElementById("refreshPortfolioBtn").addEventListener("click", refreshPortfolio);
    document.getElementById("runPortfolioBacktestBtn").addEventListener("click", startPortfolioBacktest);
    document.getElementById("downloadDatasetBtn")?.addEventListener("click", downloadDataset);
    document.getElementById("startPortfolioLiveBtn")?.addEventListener("click", startPortfolioLive);
    document.getElementById("stopPortfolioLiveBtn")?.addEventListener("click", stopPortfolioLive);
    document.getElementById("autoRefresh").addEventListener("change", () => {
      saveParams();
      configureTimer();
    });
    inputs.forEach((id) =>
      document.getElementById(id)?.addEventListener("change", () => {
        saveParams();
      }),
    );
    persistedOnlyInputs.forEach((id) => document.getElementById(id)?.addEventListener("change", saveParams));
    persistedCheckboxes
      .filter((id) => !["autoRefresh", "oneWayOpen"].includes(id))
      .forEach((id) => document.getElementById(id)?.addEventListener("change", saveParams));
    syncMonitorFromBotForm(selectedBotKey(), false);
    refreshPortfolio();
    configureTimer();
  } catch (error) {
    console.error(error);
    setStatus("脚本错误", "danger");
    text("chartHint", String(error?.message || error));
    text("botEventHint", String(error?.stack || error));
  }
});

function restoreSavedParams() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    persistedControls.forEach((id) => {
      if (!(id in saved)) return;
      const el = document.getElementById(id);
      if (!el) return;
      if (el.type === "checkbox") {
        el.checked = Boolean(saved[id]);
      } else {
        el.value = String(saved[id]);
      }
    });
  } catch (error) {
    console.warn("参数恢复失败", error);
  }
}

function saveParams() {
  try {
    const saved = {};
    persistedControls.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      saved[id] = el.type === "checkbox" ? el.checked : el.value;
    });
    localStorage.setItem(storageKey, JSON.stringify(saved));
  } catch (error) {
    console.warn("参数保存失败", error);
  }
}

function configureTimer() {
  if (autoTimer) clearInterval(autoTimer);
  if (document.getElementById("autoRefresh").checked) {
    autoTimer = setInterval(() => {
      refreshPortfolio();
    }, 8000);
  }
}

async function refresh() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  saveParams();
  setStatus("连接中", "watch");
  const params = new URLSearchParams();
  const payload = snapshotPayload();
  Object.entries(payload).forEach(([key, value]) => params.set(key, String(value)));
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 18000);
  try {
    const response = await fetch(apiUrl(`/snapshot?${params.toString()}`), { cache: "no-store", signal: controller.signal });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "snapshot failed");
    latestData = result.data;
    render(result.data);
    setStatus("已连接", result.data.strategy.state.level);
  } catch (error) {
    renderSnapshotError(error);
    setStatus("错误", "danger");
    console.error(error);
  } finally {
    clearTimeout(timeout);
    refreshInFlight = false;
  }
}

function selectedBotKey() {
  const instId = document.getElementById("instId").value;
  if (portfolioRuntimeConfig(instId) || portfolioBotForInst(instId)) return "portfolio";
  return "portfolio";
}

function syncMonitorFromBotForm(bot, overwriteInst = true) {
  const payload = portfolioMonitorConfig(document.getElementById("instId").value);
  applyConfigToMonitorFields(payload);
}

function applyConfigToMonitorFields(payload) {
  ["lower", "upper", "leverage", "gridBps", "minNetBps", "softBps", "hardBps", "mode", "adaptiveWidthBps", "adaptiveMinWidthBps", "adaptiveMaxWidthBps", "adaptiveVolMultiplier", "rangeDriftMode", "rangeDriftWeightBps", "rangeDriftMaxBps", "exchangeStopBps", "exchangeStopTriggerPxType", "exchangeStopRepriceBps"].forEach((key) => {
    const el = document.getElementById(key);
    if (el && payload[key] !== undefined) el.value = String(payload[key]);
  });
}

function portfolioMonitorConfig(instId) {
  const runtime = portfolioRuntimeConfig(instId);
  if (runtime) return { ...runtime, instId };
  const target = (latestPortfolio?.latestReport?.rebalance?.targets || []).find((item) => item.inst_id === instId);
  const last = Number(target?.last || 1);
  const halfWidth = last * 0.06;
  return {
    instId,
    lower: Math.max(0.0001, last - halfWidth).toFixed(last < 1 ? 5 : 2),
    upper: (last + halfWidth).toFixed(last < 1 ? 5 : 2),
    leverage: "3",
    gridBps: "25",
    minNetBps: "5",
    softBps: "45",
    hardBps: "80",
    mode: "adaptive",
    adaptiveWidthBps: "520",
    adaptiveMinWidthBps: "320",
    adaptiveMaxWidthBps: "1000",
    adaptiveVolMultiplier: "12",
    rangeDriftMode: "cooldown",
    rangeDriftWeightBps: "5000",
    rangeDriftMaxBps: "500",
    exchangeStopEnabled: true,
  };
}

function snapshotPayload() {
  const bot = selectedBotKey();
  const payload = bot === "portfolio" ? portfolioMonitorConfig(document.getElementById("instId").value) : { ...ethDefaults };
  const monitorKeys = ["instId", "lower", "upper", "leverage", "gridBps", "minNetBps", "softBps", "hardBps", "mode", "adaptiveWidthBps", "adaptiveMinWidthBps", "adaptiveMaxWidthBps", "adaptiveVolMultiplier", "rangeDriftMode", "rangeDriftWeightBps", "rangeDriftMaxBps", "exchangeStopBps", "exchangeStopTriggerPxType", "exchangeStopRepriceBps"];
  monitorKeys.forEach((key) => {
    const el = document.getElementById(key);
    if (el) payload[key] = el.value;
  });
  payload.exchangeStopEnabled = Boolean(payload.exchangeStopEnabled);
  return payload;
}

function render(data) {
  const market = data.market;
  const strategy = data.strategy;
  const ticker = market.ticker;
  const mark = market.mark;

  text("capturedAt", new Date(data.capturedAt).toLocaleString());
  text("title", data.params.instId);
  text(
    "subtitle",
    `${strategy.effectiveLower} - ${strategy.effectiveUpper} · ${data.params.leverage}x · ${strategy.gridCount} grids`,
  );
  text("last", fmt(ticker.last, 4));
  text("mark", fmt(mark.markPx, 4));
  text("funding", pct(market.funding.fundingRate));
  text("spread", `${strategy.book.spreadBps.toFixed(3)} bps`);
  text("netMaker", `${strategy.netMakerBps.toFixed(2)} bps`);
  renderMinNetState(strategy);
  text("avgMove", `${strategy.oneMinute.avgAbsMoveBps.toFixed(2)} bps`);
  renderTrendState(strategy.trend);
  renderPnl(data.pnl);

  text("posMode", data.account.posMode || "--");
  text("perm", data.account.perm || "--");
  text("totalEq", money(data.balance.totalEq));
  const usdt = (data.balance.details || []).find((item) => item.ccy === "USDT");
  text("usdtAvail", usdt ? money(usdt.availBal) : "--");

  text("gridCount", strategy.gridCount);
  text("step", strategy.step);
  text("makerRt", `${strategy.makerRoundTripBps.toFixed(2)} bps`);
  text("takerRt", `${strategy.takerRoundTripBps.toFixed(2)} bps`);
  text("conservativeNet", `${fmt(strategy.conservativeNetBps)} bps`);
  text("minNetPlan", `${fmt(strategy.minNetBps)} bps`);
  text("strategyMode", `${strategy.mode}${strategy.rangeNote ? ` · ${strategy.rangeNote}` : ""}`);
  text("trendFilterState", trendDetail(strategy.trend));
  text("allowedOpenSides", openSidesText(strategy.trend));
  text("effectiveRange", `${strategy.effectiveLower} / ${strategy.effectiveUpper}`);
  text("softStop", `${strategy.softLower} / ${strategy.softUpper}`);
  text("hardStop", `${strategy.hardLower} / ${strategy.hardUpper}`);
  text("minNotional", `${Number(strategy.minOrderNotional).toFixed(4)} USDT`);
  text("minMargin", `${Number(strategy.minOrderMargin).toFixed(4)} USDT`);
  text("bidDepth", `${strategy.book.bidDepth10.toFixed(2)} USDT`);
  text("askDepth", `${strategy.book.askDepth10.toFixed(2)} USDT`);
  text("chartHint", `${strategy.state.label} · ${strategy.state.action}`);
  renderSizing(strategy.sizing);
  renderRiskTargets(strategy.risk);
  const placeOrderBtn = document.getElementById("placeOrderBtn");
  if (placeOrderBtn) placeOrderBtn.disabled = !data.trading.liveEnabled;

  const stateBox = document.getElementById("stateBox");
  stateBox.textContent = strategy.state.action;
  stateBox.className = `stateBox ${strategy.state.level}`;

  renderRuntimeSummary(data, activeBotResult(data));
  renderBook(market.books);
  renderPositions(data.positions);
  renderFills(data.fills);
  updateTradeDefaults(data);
  drawChart(data);
}

function renderSnapshotError(error) {
  const isAbort = error?.name === "AbortError";
  const message = isAbort ? "OKX快照请求超时，机器人状态仍会单独刷新" : String(error?.message || error);
  text("chartHint", message);
  text("botEventHint", message);
  text("runtimeStatus", "快照异常");
  text("runtimeDetail", message);
  const bot = activeBotResult();
  if (bot?.ok) {
    renderRuntimeSummaryFromBot(bot.data);
  }
}

function renderRuntimeSummaryFromBot(bot) {
  const diagnostics = bot?.diagnostics || {};
  const summary = diagnostics.summary || {};
  const cycle = diagnostics.cycle || {};
  const openGuard = diagnostics.openGuard || {};
  const orderPlan = diagnostics.orderPlan || {};
  const rolling = diagnostics.rollingAdaptive || {};
  const sizing = diagnostics.sizing || {};
  const lastAction = (diagnostics.actions || []).at(-1);

  const runtimeCard = document.getElementById("runtimeStatusCard");
  runtimeCard.className = `runtimeCard ${summary.level || (bot?.running ? "ok" : "stopped")}`;
  text("runtimeStatus", summary.label || (bot?.running ? "运行中" : "未运行"));
  text("runtimeDetail", rolling.leverage ? rollingSummary(rolling) : summary.detail || `PID ${bot?.pid || "--"}`);
  text("riskGateStatus", gateTitle(cycle.state, diagnostics.cooldown));
  text("riskGateDetail", diagnostics.lastDecision || cycle.note || "--");
  document.getElementById("riskGateStatus").className = gateLevelFromState(cycle.state, summary.level);
  text("orderPlanStatus", `目标 ${orderPlan.desired ?? "--"} / 待补 ${orderPlan.missing ?? "--"}`);
  text("orderPlanDetail", orderPlanDetail(orderPlan, openGuard, sizing));
  text("lastActionStatus", lastAction ? actionLabel(lastAction) : "--");
  text("lastActionDetail", lastAction ? actionDetail(lastAction) : diagnostics.lastDecision || "--");
  renderActionFeed(diagnostics);
}

function setStatus(label, level) {
  const pill = document.getElementById("statusPill");
  pill.textContent = label;
  pill.className = `pill ${level || ""}`;
}

function renderBook(book) {
  const asks = (book.asks || []).slice(0, 10).reverse();
  const bids = (book.bids || []).slice(0, 10);
  document.getElementById("book").innerHTML = [
    bookTable("卖盘", asks, "ask"),
    bookTable("买盘", bids, "bid"),
  ].join("");
}

function bookTable(title, rows, side) {
  const body = rows
    .map((row) => `<tr><td class="${side}">${fmt(row[0], 4)}</td><td>${row[1]}</td><td>${row[3]}</td></tr>`)
    .join("");
  return `<table><thead><tr><th>${title}</th><th>张</th><th>单</th></tr></thead><tbody>${body}</tbody></table>`;
}

function renderPositions(positions) {
  const root = document.getElementById("positions");
  if (!positions || positions.length === 0) {
    root.innerHTML = `<div class="empty">当前没有 ${latestData?.params?.instId || "该"} 合约持仓</div>`;
    return;
  }
  const rows = positions
    .map((p) => `<tr><td>${p.posSide || "--"}</td><td>${p.pos || "0"}</td><td>${fmt(p.avgPx, 4)}</td><td>${fmt(p.upl, 4)}</td></tr>`)
    .join("");
  root.innerHTML = `<table><thead><tr><th>方向</th><th>张数</th><th>均价</th><th>未实现</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderPnl(pnl) {
  const fields = [
    ["unrealizedPnl", pnl.unrealized],
    ["realizedPnl", pnl.realized],
    ["feesPnl", pnl.fees],
    ["netRealizedPnl", pnl.netRealized],
    ["estimatedTotalPnl", pnl.estimatedTotal],
  ];
  fields.forEach(([id, value]) => {
    const el = document.getElementById(id);
    const num = Number(value);
    el.textContent = Number.isFinite(num) ? `${num.toFixed(6)} USDT` : "--";
    el.classList.toggle("positive", num > 0);
    el.classList.toggle("negative", num < 0);
  });
  text("fillCount", pnl.fillCount ?? "--");
}

function renderSizing(sizing) {
  if (!sizing) return;
  text("sizingOrderSz", `${sizing.orderSz || "--"} 张`);
  text("sizingMaxPosition", `${sizing.maxPosition || "--"} 张`);
  text("sizingOrderMargin", sizing.orderMargin ? `${Number(sizing.orderMargin).toFixed(4)} USDT` : "--");
  text("sizingBasisMargin", sizing.basisMargin ? `${Number(sizing.basisMargin).toFixed(4)} USDT` : "--");
}

function renderRiskTargets(risk) {
  if (!risk) return;
  text("riskProfitTarget", risk.profitTarget && Number(risk.profitTarget) > 0 ? `${Number(risk.profitTarget).toFixed(4)} USDT` : "--");
  text("riskLossTarget", risk.lossTarget && Number(risk.lossTarget) > 0 ? `-${Number(risk.lossTarget).toFixed(4)} USDT` : "--");
  text("riskProfitNote", risk.profitNote || "--");
  const exchangeStop = risk.exchangeStop || {};
  const exchangeStopNote = exchangeStop.enabled
    ? `交易所 ${Number(exchangeStop.bps || 0).toFixed(0)}bps/${exchangeStop.triggerPxType || "mark"}`
    : "";
  text("riskLossNote", [risk.lossNote, risk.positionLossSlBps ? `单边 ${Number(risk.positionLossSlBps).toFixed(0)} bps` : "", exchangeStopNote].filter(Boolean).join(" · ") || "--");
  const strategy = latestData?.strategy;
  const minTpProfit = Number(strategy?.minTpProfit || 0);
  const minTpBps = Number(strategy?.minTpBps || risk.minTpBps || 0);
  if (minTpProfit > 0 || minTpBps > 0) {
    const parts = [];
    if (minTpProfit > 0) parts.push(`${minTpProfit.toFixed(4)} USDT`);
    if (minTpBps > 0) parts.push(`${minTpBps.toFixed(2)} bps`);
    text("minTpProfitState", parts.join(" / "));
  } else {
    text("minTpProfitState", "--");
  }
}

function renderMinNetState(strategy) {
  const el = document.getElementById("minNetState");
  const net = Number(strategy.conservativeNetBps);
  const min = Number(strategy.minNetBps);
  if (!Number.isFinite(net) || !Number.isFinite(min)) {
    el.textContent = "--";
    el.classList.remove("positive", "negative");
    return;
  }
  el.textContent = `${net.toFixed(2)} / ${min.toFixed(2)} bps`;
  el.classList.toggle("positive", strategy.minNetOk);
  el.classList.toggle("negative", !strategy.minNetOk);
}

function renderTrendState(trend) {
  const el = document.getElementById("trendState");
  if (!trend) {
    el.textContent = "--";
    el.classList.remove("positive", "negative");
    return;
  }
  const regime = trend.regimeFilter === "ma_cross" ? `MA ${trend.regimeState}/${trend.regimeRawState} ${Number(trend.regimeDiffBps || 0).toFixed(1)}bps` : `${trend.direction} ${Number(trend.changeBps).toFixed(2)} bps`;
  el.textContent = `${regime} · ${openSidesText(trend)}`;
  el.classList.toggle("positive", trend.allowedOpenSides && trend.allowedOpenSides.length > 0);
  el.classList.toggle("negative", !trend.allowedOpenSides || trend.allowedOpenSides.length === 0);
}

function renderRuntimeSummary(data, botResult) {
  const strategy = data.strategy;
  const bot = botResult?.ok ? botResult.data : null;
  const diagnostics = bot?.diagnostics || {};
  const summary = diagnostics.summary || {};
  const cycle = diagnostics.cycle || {};
  const openGuard = diagnostics.openGuard || strategy.trend || {};
  const orderPlan = diagnostics.orderPlan || {};
  const rolling = diagnostics.rollingAdaptive || {};
  const sizing = diagnostics.sizing || {};
  const lastAction = (diagnostics.actions || []).at(-1);

  const runtimeCard = document.getElementById("runtimeStatusCard");
  runtimeCard.className = `runtimeCard ${summary.level || (bot?.running ? "ok" : "stopped")}`;
  text("runtimeStatus", summary.label || (bot?.running ? "运行中" : "未运行"));
  text("runtimeDetail", rolling.leverage ? rollingSummary(rolling) : summary.detail || (bot ? `PID ${bot.pid || "--"}` : "等待状态"));

  const gateLevel = gateLevelFromState(cycle.state || strategy.state.label, summary.level);
  text("riskGateStatus", gateTitle(cycle.state, diagnostics.cooldown));
  text("riskGateDetail", gateDetail(strategy, diagnostics, openGuard));
  document.getElementById("riskGateStatus").className = gateLevel;

  const desired = orderPlan.desired ?? "--";
  const missing = orderPlan.missing ?? "--";
  const stale = orderPlan.stale ?? "--";
  text("orderPlanStatus", `目标 ${desired} / 待补 ${missing}`);
  text("orderPlanDetail", orderPlanDetail(orderPlan, openGuard, sizing, stale));

  if (lastAction) {
    text("lastActionStatus", actionLabel(lastAction));
    text("lastActionDetail", actionDetail(lastAction));
  } else {
    text("lastActionStatus", "--");
    text("lastActionDetail", diagnostics.lastDecision || "--");
  }
  renderActionFeed(diagnostics);
}

function rollingSummary(rolling) {
  return `滚动自适应 ${fmt(rolling.leverage, 0)}x · grid ${fmt(rolling.gridBps, 2)}bps · risk ${fmt(rolling.riskScore, 3)}`;
}

function orderPlanDetail(orderPlan, openGuard, sizing, staleValue = orderPlan?.stale) {
  if (sizing && (String(sizing.orderSz) === "0" || String(sizing.maxPosition) === "0")) {
    return `开仓尺寸为 0 · ${sizing.note || "--"}`;
  }
  return `已有 ${orderPlan.existing ?? "--"} · 过期 ${staleValue ?? "--"} · 开仓 ${openSidesText(openGuard)}`;
}

function edgeSummary(edge) {
  if (!edge) return "--";
  return `${fmt(edge.netEstBps, 2)} / ${fmt(edge.minNetBps, 2)} bps`;
}

function positionSummary(cycle) {
  if (!cycle) return "--";
  return `L ${cycle.long ?? "--"} / S ${cycle.short ?? "--"}`;
}

function gateLevelFromState(state, summaryLevel) {
  if (summaryLevel === "danger" || String(state).includes("hard")) return "negative";
  if (summaryLevel === "warn" || ["soft_low", "soft_high", "buffer"].includes(state)) return "warnText";
  return "positive";
}

function gateTitle(state, cooldown) {
  if (cooldown?.active) return "冷静期";
  if (state === "hard_low" || state === "hard_high") return "硬止损";
  if (state === "soft_low" || state === "soft_high") return "软护栏";
  if (state === "buffer") return "区间缓冲";
  if (state === "inside") return "允许交易";
  return state || "--";
}

function gateDetail(strategy, diagnostics, openGuard) {
  if (diagnostics.cooldown?.active) {
    const remaining = diagnostics.cooldown.remainingSeconds;
    return `${diagnostics.cooldown.reason || "--"} · ${remaining == null ? "等待恢复" : `剩余 ${remaining}s`}`;
  }
  if (diagnostics.lastError?.text) return translateBotMessage(diagnostics.lastError.text);
  if (diagnostics.lastDecision) return translateBotMessage(diagnostics.lastDecision);
  return `${strategy.effectiveLower} - ${strategy.effectiveUpper} · 开仓 ${openSidesText(openGuard)}`;
}

function actionLabel(action) {
  if (action.kind === "place") return `${action.tag} ${action.side}/${action.posSide}`;
  if (action.kind === "cancel") return `撤单 ${action.reason}`;
  if (action.kind === "cancel_all") return `批量撤单 ${action.reason}`;
  if (action.kind === "risk") return "风控事件";
  return action.kind || "--";
}

function actionDetail(action) {
  if (action.kind === "place") return `${action.size} @ ${action.price}`;
  if (action.kind === "cancel") return action.clientOrderId || "--";
  if (action.kind === "cancel_all") return `${action.count || 0} 笔`;
  return action.text || "--";
}

function renderActionFeed(diagnostics) {
  const root = document.getElementById("botActionFeed");
  const actions = diagnostics.actions || [];
  const rolling = diagnostics.rollingAdaptive;
  const rows = actions.slice(-8).reverse().map((action) => {
    const cls = action.kind === "place" ? "place" : action.kind === "risk" ? "risk" : "cancel";
    return `<div class="actionItem ${cls}"><strong>${actionLabel(action)}</strong><span>${actionDetail(action)}</span></div>`;
  });
  if (rolling) {
    rows.unshift(`<div class="actionItem place"><strong>滚动自适应</strong><span>${esc(rollingSummary(rolling))} · vol ${fmt(rolling.avgAbsBps, 2)}bps shock ${fmt(rolling.shockBps, 2)}bps</span></div>`);
  }
  root.innerHTML = rows.length ? rows.join("") : `<div class="empty">暂无机器人动作</div>`;
  text("botEventHint", translateBotMessage(diagnostics.lastError?.text || diagnostics.lastDecision || (rolling ? rollingSummary(rolling) : "最近循环正常")));
}

async function refreshPortfolio() {
  try {
    const response = await fetch(apiUrl("/portfolio/latest?includeAccount=1&includeRegimeResearch=1"), { cache: "no-store" });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "portfolio latest failed");
    latestPortfolio = result.data;
    renderPortfolio(result.data);
    syncMonitorFromBotForm(selectedBotKey(), false);
    if (latestData) {
      renderRuntimeSummary(latestData, activeBotResult(latestData));
      drawChart(latestData);
    }
  } catch (error) {
    text("portfolioReportMeta", `组合报告读取失败：${error?.message || error}`);
    console.error(error);
  }
}

async function startPortfolioBacktest() {
  const button = document.getElementById("runPortfolioBacktestBtn");
  button.disabled = true;
  button.textContent = "回测启动中";
  try {
    const payload = portfolioBacktestPayload();
    const response = await fetch(apiUrl("/portfolio/backtest/start"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "组合回测启动失败");
    latestPortfolio = result.data;
    renderPortfolio(result.data);
  } catch (error) {
    text("portfolioReportMeta", `组合回测启动失败：${error?.message || error}`);
  } finally {
    button.disabled = false;
    button.textContent = "跑组合回测";
  }
}

async function downloadDataset() {
  const button = document.getElementById("downloadDatasetBtn");
  button.disabled = true;
  button.textContent = "打包中";
  try {
    const response = await fetch(apiUrl("/dataset/download"), { cache: "no-store" });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = await response.json();
        throw new Error(payload.error || "数据集下载失败");
      }
      throw new Error(`数据集下载失败 HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = filenameFromDisposition(response.headers.get("content-disposition")) || "okx-quant-dataset.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
    text("portfolioReportMeta", "数据集已开始下载");
  } catch (error) {
    text("portfolioReportMeta", `数据集下载失败：${error?.message || error}`);
  } finally {
    button.disabled = false;
    button.textContent = "下载数据集";
  }
}

async function startPortfolioLive() {
  const button = document.getElementById("startPortfolioLiveBtn");
  button.disabled = true;
  button.textContent = "启动中";
  try {
    const summary = latestPortfolio?.latestReport?.summary || {};
    if (summary.tradingMode !== "live") {
      throw new Error("最新组合报告不是直接实盘模式，请先选择“直接实盘”并重新跑组合回测。");
    }
    const response = await fetch(apiUrl("/portfolio/live/start"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ executeRebalance: true, tradingMode: "live" }),
    });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "组合实盘启动失败");
    latestPortfolio = result.data;
    renderPortfolio(result.data);
  } catch (error) {
    text("portfolioReportMeta", `组合实盘启动失败：${error?.message || error}`);
  } finally {
    button.disabled = false;
    button.textContent = "启动组合实盘";
  }
}

async function stopPortfolioLive() {
  const button = document.getElementById("stopPortfolioLiveBtn");
  button.disabled = true;
  button.textContent = "停止中";
  try {
    const response = await fetch(apiUrl("/portfolio/live/stop"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "组合实盘停止失败");
    latestPortfolio = result.data;
    renderPortfolio(result.data);
  } catch (error) {
    text("portfolioReportMeta", `组合实盘停止失败：${error?.message || error}`);
  } finally {
    button.disabled = false;
    button.textContent = "停止组合实盘";
  }
}

function filenameFromDisposition(value) {
  const match = String(value || "").match(/filename=\"?([^\";]+)\"?/i);
  return match ? match[1] : "";
}

function portfolioBacktestPayload() {
  const val = (id) => document.getElementById(id).value;
  return {
    tradingMode: val("portfolioTradingMode"),
    topN: val("portfolioTopN"),
    targetSymbols: val("portfolioTargetSymbols"),
    backtestPages: val("portfolioBacktestPages"),
    backtestLimit: val("portfolioBacktestLimit"),
    allocationMaxRiskEvents: val("portfolioMaxRiskEvents"),
    coreSymbols: val("portfolioCoreSymbols"),
    coreWeightSharePct: val("portfolioCoreShare"),
    satelliteMaxWeightPct: val("portfolioSatelliteMax"),
    satelliteMinWeightPct: val("portfolioSatelliteMin"),
    marketRegimeFilter: val("portfolioMarketRegimeFilter"),
    marketRegimeMinConfidence: val("portfolioMarketRegimeMinConfidence"),
    marketRegimeMixedPolicy: val("portfolioMarketRegimeMixedPolicy"),
    includeAccount: document.getElementById("portfolioIncludeAccount").checked,
    refresh: document.getElementById("portfolioRefreshData").checked,
  };
}

function renderPortfolio(data) {
  const backtest = data?.backtest || {};
  const report = data?.latestReport;
  const live = data?.live || report?.live || {};
  renderPortfolioAccount(data?.account || {});
  text("portfolioBacktestState", backtest.running ? "运行中" : backtestStateText(backtest.state, backtest.returnCode));
  text("portfolioBacktestLogAt", backtest.lastLogAt ? time(backtest.lastLogAt) : "--");
  text("portfolioLog", portfolioBacktestLogText(backtest));
  const backtestButton = document.getElementById("runPortfolioBacktestBtn");
  if (backtestButton) {
    backtestButton.disabled = Boolean(backtest.running);
    backtestButton.textContent = backtest.running ? "回测运行中" : "跑组合回测";
  }
  if (!report) {
    text("portfolioReportMeta", backtest.running ? "组合回测运行中，等待报告生成" : "暂无组合报告");
    renderPortfolioEmpty();
    return;
  }
  const summary = report.summary || {};
  const product = report.product || {};
  const productLabel = product.productCn || product.product || "豆包 Quant";
  text("portfolioReportMeta", `${productLabel} · ${report.name || "--"} · ${report.generatedAt || "--"} · ${report.reportDir || ""}`);
  text("portfolioCoreSummary", `${summary.coreCount ?? 0} 个 · ${fmt(coreWeightPct(report.rebalance?.targets || []), 2)}%`);
  text("portfolioSatelliteSummary", `${summary.satelliteCount ?? 0} 个 · ${fmt(summary.satelliteWeightPct, 2)}%`);
  text("portfolioMlRegime", mlRegimeSummary(summary, product.mlRegime));
  text("portfolioRebalanceTiming", rebalanceTimingText(report.rebalance?.actions || [], report.rebalance?.allocation || {}));
  text("portfolioAdaptiveProfile", adaptiveProfileText(summary.adaptivePreview || []));
  text("portfolioLiveState", `${summary.liveRunningCount ?? live.runningCount ?? 0} / ${summary.liveTargetCount ?? live.targetCount ?? 0}`);
  text("portfolioPreflightState", `${live.preflightStatus || report.preflight?.status || "--"} / ${live.livePlanStatus || report.livePlan?.status || "--"}`);
  const startButton = document.getElementById("startPortfolioLiveBtn");
  if (startButton) {
    startButton.disabled = summary.tradingMode !== "live";
    startButton.title = summary.tradingMode === "live" ? "启动最新直接实盘报告" : "先用直接实盘模式重新跑组合回测";
  }
  renderPortfolioDigest(report, summary);
  renderPortfolioRoleTargets(report.rebalance?.targets || [], "core", "portfolioCoreTable", report.eligibilityDiagnostics || []);
  renderPortfolioRoleTargets(report.rebalance?.targets || [], "satellite", "portfolioSatelliteTable", report.eligibilityDiagnostics || []);
  renderPortfolioActions(report.rebalance?.actions || []);
  renderPortfolioAdaptive(summary.adaptivePreview || []);
  renderRegimeResearch(data?.regimeResearch, report.runtimeConfigs || []);
  renderPortfolioLiveTable(live);
  renderQuantDingerFlow(report, summary, live, data?.regimeResearch);
}

function portfolioBacktestLogText(backtest) {
  const header = portfolioBacktestParameterText(backtest);
  const logTail = backtest?.logTail || "组合回测日志等待中";
  return header ? `${header}\n\n${logTail}` : logTail;
}

function portfolioBacktestParameterText(backtest) {
  const params = backtest?.parameters || {};
  const warnings = backtest?.parameterWarnings || [];
  const keys = Object.keys(params);
  if (!keys.length && !warnings.length) return "";
  const parts = [];
  if (keys.length) {
    parts.push(
      [
        "运行参数",
        `模式=${params.tradingMode || "--"}`,
        `候选=${params.topN ?? "--"}`,
        `目标=${params.targetSymbols ?? "--"}`,
        `K线=${params.backtestPages ?? "--"}页x${params.backtestLimit ?? "--"}`,
        `最大风险事件=${params.allocationMaxRiskEvents ?? "--"}`,
        `核心=${params.coreSymbols ?? "--"}`,
      ].join(" | "),
    );
  }
  if (warnings.length) {
    parts.push(`参数已截断: ${warnings.join("; ")}`);
  }
  return parts.join("\n");
}

function renderPortfolioAccount(accountPayload) {
  if (!accountPayload?.ok) return;
  const account = accountPayload.account || {};
  const balance = accountPayload.balance || {};
  const pnl = accountPayload.pnl || {};
  const usdt = (balance.details || []).find((item) => item.ccy === "USDT");
  text("posMode", account.posMode || "--");
  text("perm", account.perm || "--");
  text("totalEq", money(balance.totalEq));
  text("usdtAvail", usdt ? money(usdt.availBal) : "--");
  text("estimatedTotalPnl", signed(pnl.estimatedTotal, 6));
  text("netRealizedPnl", signed(pnl.netRealized, 6));
  text("realizedPnl", signed(pnl.realized, 6));
  text("unrealizedPnl", signed(pnl.unrealized, 6));
  text("feesPnl", signed(pnl.fees, 6));
  text("fillCount", `${pnl.recent24hFillCount ?? 0} / 24h`);
}

function renderPortfolioEmpty() {
  [
    "portfolioCoreSummary",
    "portfolioSatelliteSummary",
    "portfolioMlRegime",
    "portfolioRebalanceTiming",
    "portfolioAdaptiveProfile",
    "portfolioLiveState",
    "portfolioPreflightState",
    "sidePortfolioLive",
    "sideReadonlyMode",
    "qdSignal",
    "qdSignalDetail",
    "qdExecute",
    "qdExecuteDetail",
    "qdRisk",
    "qdRiskDetail",
    "qdObserve",
    "qdObserveDetail",
  ].forEach((id) => text(id, "--"));
  html("portfolioCoreTable", '<div class="empty">暂无核心舱</div>');
  html("portfolioSatelliteTable", '<div class="empty">暂无卫星仓</div>');
  html("portfolioActionsTable", '<div class="empty">暂无调仓动作</div>');
  html("portfolioAdaptiveTable", '<div class="empty">暂无自适应参数</div>');
  html("portfolioRegimeResearch", '<div class="empty">暂无状态模型报告</div>');
  html("portfolioLiveTable", '<div class="empty">暂无组合实盘目标</div>');
  renderPortfolioDigest(null, {});
  const startButton = document.getElementById("startPortfolioLiveBtn");
  if (startButton) {
    startButton.disabled = true;
    startButton.title = "暂无可启动的直接实盘报告";
  }
}

function renderPortfolioDigest(report, summary) {
  const targetText = `${summary.targetCount ?? 0} / ${fmt(summary.targetWeightPct, 2)}%`;
  const roleText = `${summary.coreCount ?? 0} / ${summary.satelliteCount ?? 0}`;
  const satText = `卫星 ${fmt(summary.satelliteWeightPct, 2)}%`;
  const actionTextValue = actionMix(summary.actionsByType);
  const exposureText = `${summary.currentExposureCount ?? 0} 个暴露 · ${fmt(summary.currentMarginPct, 2)}% 保证金`;
  const readyText = `${summary.executionReadyCount ?? 0} ready`;
  const mlText = mlRegimeSummary(summary, report?.product?.mlRegime);

  text("digestTargets", targetText);
  text("digestReport", report ? `${report.product?.productCn || "豆包 Quant"} · ${report.generatedAt || "--"}` : "--");
  text("digestRoles", roleText);
  text("digestSatelliteWeight", satText);
  text("digestActions", actionTextValue);
  text("digestExposure", `${exposureText} · ${mlText}`);
  text("sideLiveBot", "组合实盘");
  text("sidePortfolioLive", `${summary.liveRunningCount ?? 0} / ${summary.liveTargetCount ?? 0} 运行`);
  text("sideReadonlyMode", `${modeText(summary.tradingMode)} · ${summary.liveEnabled ? "控制台可写" : "实盘锁定"} · ${mlText}`);
  text("sideTargets", targetText);
  text("sideSatellites", `${summary.satelliteCount ?? 0} 个 · ${fmt(summary.satelliteWeightPct, 2)}%`);
  text("sideExecution", readyText);
  text("sideActions", actionTextValue);
}

function renderQuantDingerFlow(report, summary, live, research) {
  const mlText = mlRegimeSummary(summary, report?.product?.mlRegime);
  const actionTextValue = actionMix(summary.actionsByType);
  const running = Number(summary.liveRunningCount ?? live?.runningCount ?? 0);
  const target = Number(summary.liveTargetCount ?? live?.targetCount ?? 0);
  const preflight = live?.preflightStatus || report?.preflight?.status || "--";
  const livePlan = live?.livePlanStatus || report?.livePlan?.status || "--";
  const best = research?.bestVariant || {};

  text("qdSignal", mlText);
  text("qdSignalDetail", `${trendCheckText(summary)} · 推荐 ${regimeVariantText(best.variant || report?.product?.mlRegime?.mode || "off")}`);
  text("qdExecute", `${summary.executionReadyCount ?? 0} runtime ready`);
  text("qdExecuteDetail", `${actionTextValue} · ${modeText(summary.tradingMode)}`);
  text("qdRisk", `${preflight} / ${livePlan}`);
  text("qdRiskDetail", `交易所保护止损、单仓止损、现金保留随 runtime config 下发`);
  text("qdObserve", `${running} / ${target} 运行`);
  text("qdObserveDetail", `报告 ${report?.name || "--"} · PnL ${signedMoney(live?.pnl?.estimatedTotal || 0)}`);

  text("digestLiveBot", `${running} / ${target} 运行`);
  text("digestLiveDetail", `${preflight} / ${livePlan} · ${signedMoney(live?.pnl?.estimatedTotal || 0)}`);
}

function renderPortfolioLiveTable(live) {
  const bots = live?.bots || [];
  if (!bots.length) {
    html("portfolioLiveTable", '<div class="empty">暂无组合实盘目标</div>');
    return;
  }
  html(
    "portfolioLiveTable",
    tableHtml(
      ["合约", "动作", "角色", "状态", "PID", "每单/上限", "风控", "最近原因"],
      bots.map((bot) => {
        const runtime = bot.runtimeConfig || {};
        const diagnostics = bot.diagnostics || {};
        const sizing = diagnostics.sizing || {};
        const rolling = diagnostics.rollingAdaptive || {};
        const summary = diagnostics.summary || {};
        return [
          bot.instId,
          actionText(bot.action),
          bot.role || runtime.portfolioRole || "--",
          bot.running ? "运行中" : "未运行",
          bot.pid || "--",
          `${firstValue(sizing.orderSz, runtime.orderSz) ?? "--"} / ${firstValue(sizing.maxPosition, runtime.maxPosition) ?? "--"}`,
          rolling.riskScore ? `${fmt(rolling.riskScore, 3)} · ${fmt(rolling.positionLossSlBps, 0)}bps` : `${fmt(runtime.poolAdaptiveRiskScore, 3)} · ${fmt(runtime.positionLossSlBps, 0)}bps`,
          translateBotMessage(diagnostics.lastError?.text || diagnostics.lastDecision || summary.detail || "--"),
        ];
      }),
    ),
  );
}

function mlRegimeSummary(summary, profile) {
  const modes = summary.marketRegimeModes || [];
  const active = modes.length ? modes.map(regimeVariantText).join(",") : regimeVariantText(profile?.mode || "off");
  const count = summary.marketRegimeActiveCount ?? 0;
  const delta = summary.mlReturnDeltaVsBaseline !== "" && summary.mlReturnDeltaVsBaseline !== undefined
    ? `收益${signed(summary.mlReturnDeltaVsBaseline, 2)}% 风险${signed(summary.mlRiskEventDeltaVsBaseline, 0)}`
    : "";
  return `${active} · ${count} 标的${delta ? ` · ${delta}` : ""}`;
}

function actionMix(actionsByType) {
  const entries = Object.entries(actionsByType || {}).filter(([, value]) => value);
  if (!entries.length) return "--";
  return entries.map(([key, value]) => `${actionText(key)} ${value}`).join(" / ");
}

function coreWeightPct(targets) {
  return targets.filter((target) => target.role === "core").reduce((sum, target) => sum + Number(target.weight_pct || 0), 0);
}

function rebalanceTimingText(actions, allocation) {
  if (!actions.length) return "无动作";
  const threshold = allocation?.rebalance_threshold_pct ?? allocation?.rebalanceThresholdPct ?? "2";
  const actionable = actions.filter((item) => ["enter", "increase", "decrease", "exit"].includes(item.action)).length;
  const hold = actions.filter((item) => item.action === "hold").length;
  return `偏离 >= ${fmt(threshold, 2)}% 调仓 · ${actionable} 个执行 / ${hold} 个持有`;
}

function adaptiveProfileText(rows) {
  if (!rows.length) return "--";
  const grids = rows.map((row) => Number(row.gridBps)).filter(Number.isFinite);
  const minGrid = Math.min(...grids);
  const maxGrid = Math.max(...grids);
  const mlModes = [...new Set(rows.map((row) => row.marketRegimeFilter).filter((item) => item && item !== "off"))];
  return `高频滚动 · ${fmt(minGrid, 2)}-${fmt(maxGrid, 2)} bps${mlModes.length ? ` · ML ${mlModes.map(regimeVariantText).join(",")}` : ""}`;
}

function actionText(action) {
  return {
    enter: "进场",
    increase: "加仓",
    decrease: "减仓",
    exit: "退出",
    hold: "持有",
    ignore: "忽略",
  }[action] || action || "--";
}

function renderPortfolioScores(rows) {
  const okRows = rows.filter((row) => row.status === "ok").slice(0, 12);
  if (!okRows.length) {
    html("portfolioScores", '<div class="empty">暂无成功回测</div>');
    return;
  }
  html(
    "portfolioScores",
    tableHtml(
      ["排名", "合约", "收益%", "回撤%", "胜率%", "PF", "成交", "风险/趋势"],
      okRows.map((row) => [
        row.rank,
        row.inst_id,
        fmt(row.total_return_pct, 2),
        fmt(row.max_drawdown_pct, 2),
        fmt(row.win_rate_pct, 2),
        fmt(row.profit_factor, 2),
        row.fills,
        `${row.risk_events} · ${trendLabel(row.selected_trend_filter)} ${signed(row.trend_score_delta, 2)}`,
      ]),
    ),
  );
}

function renderPortfolioRoleTargets(targets, role, targetId, diagnostics = []) {
  const rows = targets.filter((target) => target.role === role);
  if (!rows.length) {
    html(targetId, portfolioEmptyTargetHtml(role, diagnostics));
    return;
  }
  html(
    targetId,
    tableHtml(
      ["合约", "权重%", "目标保证金", "每单/上限", "排名"],
      rows.map((target) => [
        target.inst_id,
        fmt(target.weight_pct, 2),
        fmt(target.target_margin, 4),
        `${target.order_sz || "--"} / ${target.max_position || "--"}`,
        target.rank || "--",
      ]),
    ),
  );
}

function portfolioEmptyTargetHtml(role, diagnostics) {
  const title = role === "core" ? "核心舱" : "卫星仓";
  const filtered = (diagnostics || []).filter((item) => item.status === "filtered").slice(0, 6);
  if (!filtered.length) return `<div class="empty">暂无${title}</div>`;
  return [
    `<div class="empty">暂无${title}：候选未通过组合过滤</div>`,
    tableHtml(
      ["排名", "合约", "收益%", "风险事件", "过滤原因"],
      filtered.map((item) => [
        item.rank,
        item.instId,
        fmt(item.totalReturnPct, 2),
        item.riskEvents,
        translateEligibilityReason(item.reason),
      ]),
    ),
  ].join("");
}

function translateEligibilityReason(reason) {
  return String(reason || "--")
    .replace(/risk events (\d+) > max (\d+)/g, "风险事件 $1 > 上限 $2")
    .replace(/fills (\d+) < min (\d+)/g, "成交 $1 < 最少 $2")
    .replace(/score ([^ ]+) < min ([^ ;]+)/g, "评分 $1 < 下限 $2")
    .replace("passed allocation filters", "通过组合过滤");
}

function renderPortfolioActions(actions) {
  if (!actions.length) {
    html("portfolioActionsTable", '<div class="empty">暂无调仓动作</div>');
    return;
  }
  html(
    "portfolioActionsTable",
    tableHtml(
      ["时间", "动作", "合约", "当前%", "目标%", "差值%", "差额", "原因"],
      actions.map((action) => [
        time(action.generated_at),
        actionText(action.action),
        action.inst_id,
        fmt(action.current_weight_pct, 2),
        fmt(action.target_weight_pct, 2),
        fmt(action.delta_weight_pct, 2),
        fmt(action.delta_margin, 4),
        action.reason || rebalanceReasonText(action.note, action.rebalance_threshold_pct),
      ]),
    ),
  );
}

function renderPortfolioAdaptive(rows) {
  if (!rows.length) {
    html("portfolioAdaptiveTable", '<div class="empty">暂无自适应参数</div>');
    return;
  }
  html(
    "portfolioAdaptiveTable",
    tableHtml(
      ["角色", "合约", "杠杆", "格距", "单笔TP", "总TP/SL", "单边/交易所SL", "ML状态", "回测风控", "风险/趋势", "池波动"],
      rows.map((row) => [
        row.role,
        row.instId,
        row.leverage ? `${row.leverage}x` : "--",
        `${fmt(row.gridBps, 2)} bps`,
        `${fmt(row.minTpBps, 2)} bps`,
        `${fmt(row.totalProfitTpPct, 2)}% / ${fmt(row.totalLossSlPct, 2)}%`,
        `${fmt(row.positionLossSlBps, 0)} / ${fmt(row.exchangeStopBps, 0)} bps`,
        `${regimeVariantText(row.marketRegimeFilter)} ${regimeSignalText(row.marketRegimeSignal)} ${fmt(row.marketRegimeConfidence, 2)}`,
        row.note || `${fmt(row.backtestRiskRewardScore, 3)} · ret ${fmt(row.backtestTotalReturnPct, 2)} / dd ${fmt(row.backtestMaxDrawdownPct, 2)}`,
        `${fmt(row.riskScore, 3)} · ${trendLabel(row.trendFilter)}`,
        `${fmt(row.poolAvgAbsBps, 2)} / ${fmt(row.poolShockBps, 2)} bps`,
      ]),
    ),
  );
}

function renderRegimeResearch(research, runtimeConfigs = []) {
  if (!research) {
    html("portfolioRegimeResearch", '<div class="empty">暂无状态模型报告</div>');
    return;
  }
  const best = research.bestVariant || {};
  const activeModes = [...new Set(runtimeConfigs.map((item) => item.marketRegimeFilter || "off"))].join(", ") || "off";
  const summaryRows = [
    ["报告", `${research.name || "--"} · ${research.generatedAt || "--"}`],
      ["当前实盘开关", `${activeModes} · ${mixedPolicyText(runtimeConfigs[0]?.marketRegimeMixedPolicy)}`],
    ["推荐研究层", regimeVariantText(best.variant)],
    ["收益/回撤变化", `${signed(best.returnDeltaVsBaseline, 2)}% / ${signed(best.drawdownDeltaVsBaseline, 2)}%`],
    ["风险事件变化", signed(best.riskEventDeltaVsBaseline, 0)],
    ["RF/HMM 弱标签", `${fmt(research.models?.rf?.accuracy, 3)} / ${fmt(research.models?.hmm?.accuracyVsWeakLabels, 3)}`],
    ["QuantDinger", `${research.quantDinger?.license || "--"} · 标准已参考，未接管实盘执行`],
  ];
  const variantRows = (research.variantSummary || []).map((row) => [
    regimeVariantText(row.variant),
    row.symbols,
    fmt(row.avgReturnPct, 2),
    fmt(row.avgMaxDrawdownPct, 2),
    fmt(row.avgScore, 2),
    row.totalRiskEvents,
  ]);
  const topRows = (research.topRows || [])
    .filter((row) => row.variant === best.variant)
    .slice(0, 6)
    .map((row) => [
      row.instId,
      fmt(row.totalReturnPct, 2),
      fmt(row.maxDrawdownPct, 2),
      row.fills,
      row.riskEvents,
      `${regimeSignalText(row.latestSignal)} ${fmt(row.latestConfidence, 2)}`,
    ]);
  html(
    "portfolioRegimeResearch",
    [
      tableHtml(["项目", "值"], summaryRows),
      variantRows.length ? tableHtml(["方案", "标的", "均收益%", "均回撤%", "均分", "风险"], variantRows) : "",
      topRows.length ? tableHtml(["合约", "收益%", "回撤%", "成交", "风险", "最新"], topRows) : "",
    ].join(""),
  );
}

function regimeVariantText(variant) {
  return {
    baseline: "基线",
    rules: "规则",
    rf: "RF",
    hmm: "HMM",
  }[variant] || variant || "--";
}

function regimeSignalText(signal) {
  return {
    off: "关闭",
    range: "震荡",
    mixed: "混合",
    trend_up: "上行趋势",
    trend_down: "下行趋势",
  }[signal] || signal || "--";
}

function mixedPolicyText(policy) {
  return {
    pause: "混合暂停",
    price_anchor: "混合价格锚定",
    range: "混合双向网格",
  }[policy] || policy || "混合价格锚定";
}

function rebalanceReasonText(note, threshold = "2") {
  return {
    "new target allocation": `进入目标组合，偏离达到 ${fmt(threshold, 2)}% 阈值时建仓`,
    "below target allocation": `当前权重低于目标，偏离达到 ${fmt(threshold, 2)}% 阈值时加仓`,
    "above target allocation": `当前权重高于目标，偏离达到 ${fmt(threshold, 2)}% 阈值时减仓`,
    "not selected by target portfolio": "不在目标组合内时退出",
    "within threshold": `偏离未超过 ${fmt(threshold, 2)}% 阈值，暂不调仓`,
  }[note] || note || "--";
}

function backtestStateText(state, returnCode) {
  if (state === "running") return "运行中";
  if (state === "completed" || returnCode === 0) return "完成";
  if (state === "failed" || returnCode != null) return returnCode == null ? "失败" : `退出 ${returnCode}`;
  if (state === "unknown") return "日志未完成";
  return "空闲";
}

function modeText(mode) {
  return {
    live: "直接实盘",
    paper: "回测沙盘",
    backtest: "仅回测",
  }[mode] || mode || "--";
}

function basename(path) {
  return String(path || "").split("/").filter(Boolean).at(-1) || "--";
}

function trendDetail(trend) {
  if (!trend) return "--";
  if (trend.regimeFilter === "ma_cross") {
    return `MA ${trend.regimeState}/${trend.regimeRawState} · ${Number(trend.regimeDiffBps || 0).toFixed(1)} bps`;
  }
  return `${trend.filter} · ${trend.direction} · ${Number(trend.changeBps).toFixed(2)} bps/${trend.thresholdBps}`;
}

function openSidesText(trend) {
  const sides = trend?.allowedOpenSides || trend?.sides || [];
  if (!sides.length) return "close-only";
  return sides.join(",");
}

function renderFills(fills) {
  const root = document.getElementById("fills");
  if (!fills || fills.length === 0) {
    root.innerHTML = `<div class="empty">暂无成交</div>`;
    return;
  }
  const rows = fills
    .slice(0, 12)
    .map((f) => {
      const pnl = Number(f.fillPnl || 0) + Number(f.fee || 0);
      const cls = pnl > 0 ? "positive" : pnl < 0 ? "negative" : "";
      return `<tr><td>${time(f.fillTime)}</td><td>${f.side}</td><td>${f.posSide}</td><td>${fmt(f.fillPx, 4)}</td><td>${f.fillSz}</td><td class="${cls}">${pnl.toFixed(6)}</td></tr>`;
    })
    .join("");
  root.innerHTML = `<table><thead><tr><th>时间</th><th>方向</th><th>持仓</th><th>价格</th><th>张数</th><th>净收益</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function updateTradeDefaults(data) {
  const intent = document.getElementById("tradeIntent")?.value;
  const px = document.getElementById("tradePx");
  if (!intent || !px) return;
  const lower = Number(data.params.lower);
  const upper = Number(data.params.upper);
  const step = Number(data.strategy.step);
  if (document.activeElement === px) return;
  if (intent === "openLong") px.value = lower.toFixed(4);
  if (intent === "openShort") px.value = upper.toFixed(4);
  if (intent === "closeLong") px.value = (lower + step).toFixed(4);
  if (intent === "closeShort") px.value = (upper - step).toFixed(4);
}

function activeBotResult(data = latestData) {
  const instId = data?.params?.instId || document.getElementById("instId")?.value;
  const portfolioBot = portfolioBotForInst(instId);
  if (portfolioBot) return { ok: true, data: portfolioBot };
  return null;
}

function portfolioBotForInst(instId) {
  const live = latestPortfolio?.live || latestPortfolio?.latestReport?.live || {};
  const bot = (live.bots || []).find((item) => item.instId === instId);
  if (!bot) return null;
  return {
    ...bot,
    source: "portfolio",
    readOnly: true,
    botPrefix: bot.botPrefix || portfolioPrefixForInst(instId),
    runtimeConfig: bot.runtimeConfig || portfolioRuntimeConfig(instId) || {},
  };
}

function portfolioRuntimeConfig(instId) {
  return (latestPortfolio?.latestReport?.runtimeConfigs || []).find((item) => item.instId === instId);
}

function drawChart(data) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const candles = data.market.candles || [];
  if (!candles.length) return;

  const strategy = data.strategy;
  const botResult = activeBotResult(data);
  const bot = botResult?.ok ? botResult.data : null;
  const diagnostics = bot?.diagnostics || {};
  const prices = candles.flatMap((c) => [c.high, c.low]);
  [
    strategy.effectiveLower,
    strategy.effectiveUpper,
    strategy.outerLower,
    strategy.outerUpper,
    strategy.softLower,
    strategy.softUpper,
    strategy.hardLower,
    strategy.hardUpper,
  ].forEach((value) => prices.push(Number(value)));

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const pad = (max - min) * 0.08 || 0.01;
  const yMin = min - pad;
  const yMax = max + pad;
  const left = 54;
  const right = 18;
  const top = 24;
  const bottom = 34;
  const plotW = w - left - right;
  const plotH = h - top - bottom;

  const x = (i) => left + (i / Math.max(1, candles.length - 1)) * plotW;
  const y = (price) => top + ((yMax - price) / (yMax - yMin)) * plotH;

  ctx.strokeStyle = "#e8eeea";
  ctx.lineWidth = 1;
  ctx.font = "12px Segoe UI";
  ctx.fillStyle = "#637069";
  for (let i = 0; i <= 5; i++) {
    const py = top + (plotH / 5) * i;
    ctx.beginPath();
    ctx.moveTo(left, py);
    ctx.lineTo(w - right, py);
    ctx.stroke();
    const price = yMax - ((yMax - yMin) / 5) * i;
    ctx.fillText(price.toFixed(4), 8, py + 4);
  }

  drawRegimeBackground(ctx, strategy, diagnostics, left, top, plotW, plotH);

  drawLine(ctx, y(Number(strategy.effectiveLower)), left, w - right, "#2563eb", "实时下沿");
  drawLine(ctx, y(Number(strategy.effectiveUpper)), left, w - right, "#2563eb", "实时上沿");
  if (strategy.mode === "adaptive") {
    drawLine(ctx, y(Number(strategy.outerLower)), left, w - right, "#8b95a1", "护栏下沿");
    drawLine(ctx, y(Number(strategy.outerUpper)), left, w - right, "#8b95a1", "护栏上沿");
  }
  drawLine(ctx, y(Number(strategy.softLower)), left, w - right, "#b7791f", "软止损");
  drawLine(ctx, y(Number(strategy.softUpper)), left, w - right, "#b7791f", "软止损");
  drawLine(ctx, y(Number(strategy.hardLower)), left, w - right, "#c2413b", "硬止损");
  drawLine(ctx, y(Number(strategy.hardUpper)), left, w - right, "#c2413b", "硬止损");

  ctx.strokeStyle = "rgba(22,129,122,0.2)";
  strategy.gridLines.forEach((line) => {
    const py = y(Number(line.price));
    ctx.beginPath();
    ctx.moveTo(left, py);
    ctx.lineTo(w - right, py);
    ctx.stroke();
  });

  const candleW = Math.max(3, plotW / candles.length * 0.58);
  candles.forEach((c, i) => {
    const cx = x(i);
    const up = c.close >= c.open;
    ctx.strokeStyle = up ? "#1d8f61" : "#c2413b";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath();
    ctx.moveTo(cx, y(c.high));
    ctx.lineTo(cx, y(c.low));
    ctx.stroke();
    const bodyTop = y(Math.max(c.open, c.close));
    const bodyH = Math.max(1, Math.abs(y(c.open) - y(c.close)));
    ctx.fillRect(cx - candleW / 2, bodyTop, candleW, bodyH);
  });

  drawPositions(ctx, data.positions || [], y, left, w - right);
  drawFills(ctx, data.fills || [], candles, x, y);

  const last = Number(data.market.ticker.last);
  drawLine(ctx, y(last), left, w - right, "#1c2421", `last ${last.toFixed(4)}`, true);
  drawStatusBadge(ctx, diagnostics.summary, left, top, w - right);
}

function drawRegimeBackground(ctx, strategy, diagnostics, left, top, plotW, plotH) {
  const state = diagnostics.cycle?.state || strategy.state?.level;
  const summary = diagnostics.summary || {};
  let color = "rgba(29, 143, 97, 0.035)";
  if (summary.level === "warn" || ["soft_low", "soft_high", "buffer"].includes(state)) color = "rgba(183, 121, 31, 0.08)";
  if (summary.level === "danger" || ["hard_low", "hard_high"].includes(state)) color = "rgba(194, 65, 59, 0.09)";
  ctx.save();
  ctx.fillStyle = color;
  ctx.fillRect(left, top, plotW, plotH);
  ctx.restore();
}

function drawPositions(ctx, positions, y, x1, x2) {
  positions.forEach((position) => {
    const avg = Number(position.avgPx);
    const size = Number(position.pos);
    if (!Number.isFinite(avg) || !size) return;
    const color = position.posSide === "long" ? "#1d8f61" : "#c2413b";
    drawLine(ctx, y(avg), x1, x2, color, `${position.posSide} avg ${avg.toFixed(4)}`, true);
  });
}

function portfolioPrefixForInst(instId) {
  const base = String(instId || "").split("-")[0].toLowerCase();
  return base ? `p${base}`.slice(0, 8) : "";
}

function drawFills(ctx, fills, candles, x, y) {
  if (!fills || !fills.length || !candles.length) return;
  const firstTs = candles[0].ts;
  const lastTs = candles[candles.length - 1].ts;
  const width = Math.max(1, lastTs - firstTs);
  fills.slice(0, 20).forEach((fill) => {
    const timeValue = Number(fill.fillTime);
    const price = Number(fill.fillPx);
    if (!Number.isFinite(timeValue) || !Number.isFinite(price) || timeValue < firstTs) return;
    const index = Math.max(0, Math.min(candles.length - 1, ((timeValue - firstTs) / width) * (candles.length - 1)));
    const px = x(index);
    const py = y(price);
    ctx.save();
    ctx.fillStyle = fill.side === "buy" ? "#1d8f61" : "#c2413b";
    ctx.beginPath();
    ctx.moveTo(px, py - 6);
    ctx.lineTo(px + 5, py + 5);
    ctx.lineTo(px - 5, py + 5);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  });
}

function drawStatusBadge(ctx, summary, x1, y1, x2) {
  if (!summary) return;
  const label = `${summary.label || "--"} · ${summary.detail || ""}`.slice(0, 72);
  const color = summary.level === "danger" ? "#c2413b" : summary.level === "warn" ? "#b7791f" : summary.level === "stopped" ? "#637069" : "#1d8f61";
  ctx.save();
  ctx.font = "12px Segoe UI";
  const width = Math.min(x2 - x1 - 10, ctx.measureText(label).width + 18);
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(x1 + 8, y1 + 8, width, 28, 6);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.fillText(label, x1 + 17, y1 + 27);
  ctx.restore();
}

function drawLine(ctx, py, x1, x2, color, label, strong = false) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = strong ? 2 : 1;
  ctx.setLineDash(strong ? [] : [5, 5]);
  ctx.beginPath();
  ctx.moveTo(x1, py);
  ctx.lineTo(x2, py);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.font = "12px Segoe UI";
  ctx.fillText(label, x2 - 96, py - 5);
  ctx.restore();
}

function text(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "--";
}

function html(id, value) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = value;
}

function tableHtml(headers, rows) {
  return `<table><thead><tr>${headers.map((header) => `<th>${esc(header)}</th>`).join("")}</tr></thead><tbody>${rows
    .map((row) => `<tr>${row.map((item) => `<td>${esc(item)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function esc(value) {
  return String(value ?? "--")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmt(value, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : "--";
}

function pct(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${(num * 100).toFixed(4)}%` : "--";
}

function money(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(4)}` : "--";
}

function signed(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "--";
  return `${num >= 0 ? "+" : ""}${num.toFixed(digits)}`;
}

function signedMoney(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "--";
  return `${num >= 0 ? "+" : ""}${num.toFixed(6)} USDT`;
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function trendLabel(value) {
  return value === "auto" ? "趋势自动" : value === "off" ? "趋势关闭" : value || "--";
}

function trendCheckText(summary) {
  const checked = summary.trendCheckedCount ?? 0;
  const auto = summary.trendAutoSelectedCount ?? 0;
  const off = summary.trendOffSelectedCount ?? 0;
  return checked ? `已检查 ${checked} · 自动 ${auto} / 关闭 ${off}` : "--";
}

function translateBotMessage(message) {
  const textValue = String(message || "--");
  if (/Rolling adaptive leverage sync failed/i.test(textValue) || /OKX API error 59108/i.test(textValue)) {
    return "杠杆同步失败：账户杠杆偏低或保证金不足，本轮不下单。请提高该合约杠杆，或降低每单保证金、仓位上限后再观察。";
  }
  if (/Net edge too low/i.test(textValue)) {
    return "净收益空间不足：本轮不新增开仓挂单，已有平仓挂单会继续维护。";
  }
  if (/Risk cooldown active/i.test(textValue)) {
    return "风控冷静期中：暂缓新增交易，等待冷静期结束。";
  }
  if (/Price hard stop/i.test(textValue)) {
    return "价格触发硬止损：等待平仓或风控恢复。";
  }
  if (/OKX error|Bot error/i.test(textValue)) {
    return `机器人错误：${textValue.replace(/^Bot error:\s*/i, "").replace(/^OKX error:\s*/i, "")}`;
  }
  return textValue;
}

function time(ms) {
  if (typeof ms === "string" && ms.trim()) {
    const parsed = new Date(ms);
    if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString();
  }
  const num = Number(ms);
  return Number.isFinite(num) ? new Date(num).toLocaleTimeString() : "--";
}
