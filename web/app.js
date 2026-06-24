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
const storageKey = "okxQuantConsole.params.v1";
const persistedOnlyInputs = [
  "missedTpOrdType",
  "missedTpSlippageBps",
];
const persistedCheckboxes = [
  "autoRefresh",
];
const persistedControls = [...new Set([...inputs, ...persistedOnlyInputs, ...persistedCheckboxes])];
const botFieldMap = {
  lower: "Lower",
  upper: "Upper",
  leverage: "Leverage",
  orderSz: "OrderSz",
  maxPosition: "MaxPosition",
  orderMarginPct: "OrderMarginPct",
  maxMarginPct: "MaxMarginPct",
  maxOpenOrdersPerSide: "MaxOrders",
  interval: "Interval",
  minTpBps: "MinTpBps",
  positionLossSlBps: "PositionLossSlBps",
  exchangeStopBps: "ExchangeStopBps",
  exchangeStopTriggerPxType: "ExchangeStopTriggerPxType",
  exchangeStopRepriceBps: "ExchangeStopRepriceBps",
  regimeFilter: "RegimeFilter",
  regimeBar: "RegimeBar",
  regimeShortMa: "RegimeShortMa",
  regimeLongMa: "RegimeLongMa",
  regimeDiffBps: "RegimeDiffBps",
  regimeConfirmBars: "RegimeConfirmBars",
};
const botDefaults = {
  beat: {
    instId: "BEAT-USDT-SWAP",
    lower: "1.74",
    upper: "1.84",
    leverage: "3",
    gridBps: "25",
    minNetBps: "5",
    softBps: "45",
    hardBps: "80",
    mode: "adaptive",
    adaptiveWidthBps: "520",
    adaptiveMinWidthBps: "320",
    adaptiveMaxWidthBps: "850",
    adaptiveVolMultiplier: "12",
    rangeDriftMode: "cooldown",
    rangeDriftWeightBps: "2500",
    rangeDriftMaxBps: "250",
    sizingMode: "margin_pct",
    orderSz: "0.1",
    maxPosition: "0.6",
    orderMarginPct: "30",
    maxMarginPct: "55",
    maxOpenOrdersPerSide: "1",
    maxActionsPerCycle: "4",
    interval: "8",
    ordType: "post_only",
    trendFilter: "off",
    trendLookback: "8",
    trendThresholdBps: "90",
    regimeFilter: "ma_cross",
    regimeBar: "15m",
    regimeShortMa: "5",
    regimeLongMa: "20",
    regimeDiffBps: "50",
    regimeConfirmBars: "3",
    totalProfitTp: "0",
    totalProfitTpPct: "6",
    totalProfitTpCap: "0.7",
    totalProfitAction: "checkpoint",
    minTpProfit: "0.01",
    minTpBps: "160",
    totalLossSl: "0",
    totalLossSlPct: "3",
    totalLossSlCap: "0.5",
    positionLossSlBps: "550",
    exchangeStopEnabled: false,
    exchangeStopBps: "650",
    exchangeStopTriggerPxType: "mark",
    exchangeStopRepriceBps: "5",
    missedTpOrdType: "limit",
    missedTpSlippageBps: "20",
    hardStopOrdType: "market",
    hardStopSlippageBps: "50",
    riskCooldown: "60",
    recenterOnCooldown: true,
    oneWayOpen: true,
    cancelOnStop: true,
  },
  re: {
    instId: "RE-USDT-SWAP",
    lower: "0.78",
    upper: "0.88",
    leverage: "5",
    gridBps: "25",
    minNetBps: "5",
    softBps: "45",
    hardBps: "80",
    mode: "adaptive",
    adaptiveWidthBps: "420",
    adaptiveMinWidthBps: "260",
    adaptiveMaxWidthBps: "700",
    adaptiveVolMultiplier: "12",
    rangeDriftMode: "cooldown",
    rangeDriftWeightBps: "2500",
    rangeDriftMaxBps: "250",
    sizingMode: "margin_pct",
    orderSz: "1",
    maxPosition: "1",
    orderMarginPct: "10",
    maxMarginPct: "30",
    maxOpenOrdersPerSide: "1",
    maxActionsPerCycle: "3",
    interval: "8",
    ordType: "post_only",
    trendFilter: "off",
    trendLookback: "8",
    trendThresholdBps: "90",
    regimeFilter: "ma_cross",
    regimeBar: "15m",
    regimeShortMa: "5",
    regimeLongMa: "20",
    regimeDiffBps: "50",
    regimeConfirmBars: "3",
    totalProfitTp: "0",
    totalProfitTpPct: "5",
    totalProfitTpCap: "0.5",
    totalProfitAction: "checkpoint",
    minTpProfit: "0",
    minTpBps: "180",
    totalLossSl: "0",
    totalLossSlPct: "3",
    totalLossSlCap: "0.5",
    positionLossSlBps: "550",
    exchangeStopEnabled: false,
    exchangeStopBps: "650",
    exchangeStopTriggerPxType: "mark",
    exchangeStopRepriceBps: "5",
    missedTpOrdType: "limit",
    missedTpSlippageBps: "20",
    hardStopOrdType: "market",
    hardStopSlippageBps: "50",
    riskCooldown: "60",
    recenterOnCooldown: true,
    oneWayOpen: true,
    cancelOnStop: true,
  },
};
let autoTimer = null;
let botTimer = null;
let latestData = null;
let latestBot = null;
let latestReBot = null;
let refreshInFlight = false;

window.addEventListener("DOMContentLoaded", () => {
  try {
    restoreSavedParams();
    document.getElementById("refreshBtn").addEventListener("click", refresh);
    document.getElementById("previewOrderBtn").addEventListener("click", () => submitOrder(true));
    document.getElementById("placeOrderBtn").addEventListener("click", () => submitOrder(false));
    document.getElementById("instId").addEventListener("change", () => {
      syncMonitorFromBotForm(selectedBotKey());
      saveParams();
      refresh();
    });
    document.getElementById("loadBeatConfigBtn").addEventListener("click", loadBeatConfig);
    document.getElementById("startBotBtn").addEventListener("click", startBot);
    document.getElementById("updateBotBtn").addEventListener("click", updateBotConfig);
    document.getElementById("stopBotBtn").addEventListener("click", stopBot);
    document.getElementById("loadReBotConfigBtn").addEventListener("click", loadReBotConfig);
    document.getElementById("dryRunReBotBtn").addEventListener("click", dryRunReBotOnce);
    document.getElementById("startReBotBtn").addEventListener("click", startReBot);
    document.getElementById("updateReBotBtn").addEventListener("click", updateReBotConfig);
    document.getElementById("stopReBotBtn").addEventListener("click", stopReBot);
    document.getElementById("autoRefresh").addEventListener("change", () => {
      saveParams();
      configureTimer();
    });
    inputs.forEach((id) =>
      document.getElementById(id)?.addEventListener("change", () => {
        saveParams();
        refresh();
      }),
    );
    persistedOnlyInputs.forEach((id) => document.getElementById(id)?.addEventListener("change", saveParams));
    persistedCheckboxes
      .filter((id) => !["autoRefresh", "oneWayOpen"].includes(id))
      .forEach((id) => document.getElementById(id)?.addEventListener("change", saveParams));
    ["beat", "re"].forEach((bot) => {
      Object.values(botFieldMap).forEach((suffix) => document.getElementById(`${bot}${suffix}`)?.addEventListener("change", () => saveBotForm(bot)));
      ["BotLive", "SetLeverage", "CancelOnStop", "ExchangeStopEnabled", "RecenterOnCooldown", "OneWayOpen", "ConfirmLive"].forEach((suffix) =>
        document.getElementById(`${bot}${suffix}`)?.addEventListener("change", () => saveBotForm(bot)),
      );
    });
    applySavedBotForms();
    syncMonitorFromBotForm(selectedBotKey(), false);
    refresh();
    refreshBotStatus();
    refreshReBotStatus();
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

function applySavedBotForms() {
  ["beat", "re"].forEach((bot) => {
    try {
      const saved = JSON.parse(localStorage.getItem(`${storageKey}.${bot}`) || "{}");
      applyConfigToBotForm(bot, { ...botDefaults[bot], ...saved });
    } catch (error) {
      applyConfigToBotForm(bot, botDefaults[bot]);
    }
  });
}

function saveBotForm(bot) {
  try {
    localStorage.setItem(`${storageKey}.${bot}`, JSON.stringify(readBotForm(bot)));
  } catch (error) {
    console.warn("机器人参数保存失败", bot, error);
  }
}

function configureTimer() {
  if (autoTimer) clearInterval(autoTimer);
  if (botTimer) clearInterval(botTimer);
  if (document.getElementById("autoRefresh").checked) {
    autoTimer = setInterval(refresh, 8000);
    botTimer = setInterval(() => {
      refreshBotStatus();
      refreshReBotStatus();
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
    const response = await fetch(`/api/snapshot?${params.toString()}`, { cache: "no-store", signal: controller.signal });
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
  return document.getElementById("instId").value === "RE-USDT-SWAP" ? "re" : "beat";
}

function syncMonitorFromBotForm(bot, overwriteInst = true) {
  const payload = buildBotPayload(bot);
  if (overwriteInst) document.getElementById("instId").value = payload.instId;
  ["lower", "upper", "leverage", "gridBps", "minNetBps", "softBps", "hardBps", "mode", "adaptiveWidthBps", "adaptiveMinWidthBps", "adaptiveMaxWidthBps", "adaptiveVolMultiplier", "rangeDriftMode", "rangeDriftWeightBps", "rangeDriftMaxBps", "exchangeStopBps", "exchangeStopTriggerPxType", "exchangeStopRepriceBps"].forEach((key) => {
    const el = document.getElementById(key);
    if (el && payload[key] !== undefined) el.value = String(payload[key]);
  });
}

function snapshotPayload() {
  const bot = selectedBotKey();
  const payload = buildBotPayload(bot);
  const monitorKeys = ["instId", "lower", "upper", "leverage", "gridBps", "minNetBps", "softBps", "hardBps", "mode", "adaptiveWidthBps", "adaptiveMinWidthBps", "adaptiveMaxWidthBps", "adaptiveVolMultiplier", "rangeDriftMode", "rangeDriftWeightBps", "rangeDriftMaxBps", "exchangeStopBps", "exchangeStopTriggerPxType", "exchangeStopRepriceBps"];
  monitorKeys.forEach((key) => {
    const el = document.getElementById(key);
    if (el) payload[key] = el.value;
  });
  payload.exchangeStopEnabled = Boolean(readBotForm(bot).exchangeStopEnabled);
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
  document.getElementById("placeOrderBtn").disabled = !data.trading.liveEnabled;

  const stateBox = document.getElementById("stateBox");
  stateBox.textContent = strategy.state.action;
  stateBox.className = `stateBox ${strategy.state.level}`;

  renderRuntimeSummary(data, activeBotResult(data));
  renderBook(market.books);
  renderPositions(data.positions);
  renderPendingOrders(data.pendingOrders);
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
  const lastAction = (diagnostics.actions || []).at(-1);

  const runtimeCard = document.getElementById("runtimeStatusCard");
  runtimeCard.className = `runtimeCard ${summary.level || (bot?.running ? "ok" : "stopped")}`;
  text("runtimeStatus", summary.label || (bot?.running ? "运行中" : "未运行"));
  text("runtimeDetail", summary.detail || `PID ${bot?.pid || "--"}`);
  text("riskGateStatus", gateTitle(cycle.state, diagnostics.cooldown));
  text("riskGateDetail", diagnostics.lastDecision || cycle.note || "--");
  document.getElementById("riskGateStatus").className = gateLevelFromState(cycle.state, summary.level);
  text("orderPlanStatus", `目标 ${orderPlan.desired ?? "--"} / 待补 ${orderPlan.missing ?? "--"}`);
  text("orderPlanDetail", `已有 ${orderPlan.existing ?? "--"} · 过期 ${orderPlan.stale ?? "--"} · 开仓 ${openSidesText(openGuard)}`);
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
  const lastAction = (diagnostics.actions || []).at(-1);

  const runtimeCard = document.getElementById("runtimeStatusCard");
  runtimeCard.className = `runtimeCard ${summary.level || (bot?.running ? "ok" : "stopped")}`;
  text("runtimeStatus", summary.label || (bot?.running ? "运行中" : "未运行"));
  text("runtimeDetail", summary.detail || (bot ? `PID ${bot.pid || "--"}` : "等待状态"));

  const gateLevel = gateLevelFromState(cycle.state || strategy.state.label, summary.level);
  text("riskGateStatus", gateTitle(cycle.state, diagnostics.cooldown));
  text("riskGateDetail", gateDetail(strategy, diagnostics, openGuard));
  document.getElementById("riskGateStatus").className = gateLevel;

  const desired = orderPlan.desired ?? "--";
  const missing = orderPlan.missing ?? "--";
  const stale = orderPlan.stale ?? "--";
  text("orderPlanStatus", `目标 ${desired} / 待补 ${missing}`);
  text("orderPlanDetail", `已有 ${orderPlan.existing ?? "--"} · 过期 ${stale} · 开仓 ${openSidesText(openGuard)}`);

  if (lastAction) {
    text("lastActionStatus", actionLabel(lastAction));
    text("lastActionDetail", actionDetail(lastAction));
  } else {
    text("lastActionStatus", "--");
    text("lastActionDetail", diagnostics.lastDecision || "--");
  }
  renderActionFeed(diagnostics);
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
  if (diagnostics.lastDecision) return diagnostics.lastDecision;
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
  const rows = actions.slice(-8).reverse().map((action) => {
    const cls = action.kind === "place" ? "place" : action.kind === "risk" ? "risk" : "cancel";
    return `<div class="actionItem ${cls}"><strong>${actionLabel(action)}</strong><span>${actionDetail(action)}</span></div>`;
  });
  root.innerHTML = rows.length ? rows.join("") : `<div class="empty">暂无机器人动作</div>`;
  text("botEventHint", diagnostics.lastError?.text || diagnostics.lastDecision || "最近循环正常");
}

function trendDetail(trend) {
  if (!trend) return "--";
  if (trend.regimeFilter === "ma_cross") {
    return `MA ${trend.regimeState}/${trend.regimeRawState} · ${Number(trend.regimeDiffBps || 0).toFixed(1)} bps`;
  }
  return `${trend.filter} · ${trend.direction} · ${Number(trend.changeBps).toFixed(2)} bps/${trend.thresholdBps}`;
}

function openSidesText(trend) {
  if (!trend || !trend.allowedOpenSides || trend.allowedOpenSides.length === 0) return "close-only";
  return trend.allowedOpenSides.join(",");
}

function renderPendingOrders(orders) {
  const root = document.getElementById("pendingOrders");
  if (!orders || orders.length === 0) {
    root.innerHTML = `<div class="empty">当前没有挂单</div>`;
    return;
  }
  const rows = orders
    .map((o) => `<tr><td>${o.posSide || "--"}</td><td>${o.side || "--"}</td><td>${fmt(o.px, 4)}</td><td>${o.sz || "0"}</td></tr>`)
    .join("");
  root.innerHTML = `<table><thead><tr><th>持仓</th><th>方向</th><th>价格</th><th>张数</th></tr></thead><tbody>${rows}</tbody></table>`;
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
  const intent = document.getElementById("tradeIntent").value;
  const lower = Number(data.params.lower);
  const upper = Number(data.params.upper);
  const step = Number(data.strategy.step);
  const px = document.getElementById("tradePx");
  if (document.activeElement === px) return;
  if (intent === "openLong") px.value = lower.toFixed(4);
  if (intent === "openShort") px.value = upper.toFixed(4);
  if (intent === "closeLong") px.value = (lower + step).toFixed(4);
  if (intent === "closeShort") px.value = (upper - step).toFixed(4);
}

async function submitOrder(dryRun) {
  if (!latestData) return;
  const payload = buildOrderPayload(dryRun);
  const endpoint = dryRun ? "/api/trade/preview" : "/api/trade/order";
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    document.getElementById("tradeResult").textContent = JSON.stringify(result, null, 2);
    if (result.ok && !dryRun) refresh();
  } catch (error) {
    document.getElementById("tradeResult").textContent = String(error);
  }
}

function buildOrderPayload(dryRun) {
  const intent = document.getElementById("tradeIntent").value;
  const map = {
    openLong: { side: "buy", posSide: "long", reduceOnly: false },
    openShort: { side: "sell", posSide: "short", reduceOnly: false },
    closeLong: { side: "sell", posSide: "long", reduceOnly: true },
    closeShort: { side: "buy", posSide: "short", reduceOnly: true },
  };
  const mapped = map[intent];
  const payload = {
    instId: document.getElementById("instId").value,
    tdMode: "cross",
    ordType: document.getElementById("ordType").value,
    px: document.getElementById("tradePx").value,
    sz: document.getElementById("tradeSz").value,
    dryRun,
    confirm: document.getElementById("confirmText").value,
    ...mapped,
  };
  return payload;
}

async function startBot() {
  saveBotForm("beat");
  const payload = buildBotPayload("beat");
  setBotUiState("starting", "启动中", "正在创建机器人进程");
  try {
    setBotButtons(false, true);
    const response = await fetch("/api/bot/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    renderBotStatus(result);
    if (result.ok) {
      setTimeout(refreshBotStatus, 1200);
    }
  } catch (error) {
    renderBotError(error);
  }
}

async function stopBot() {
  setBotUiState("stopping", "停止中", "正在结束机器人进程");
  try {
    setBotButtons(true, true);
    const response = await fetch("/api/bot/stop", { method: "POST" });
    const result = await response.json();
    renderBotStatus(result);
  } catch (error) {
    renderBotError(error);
  }
}

async function updateBotConfig() {
  saveBotForm("beat");
  const payload = buildBotPayload("beat");
  setBotUiState("starting", "应用中", "正在热更新机器人参数");
  try {
    const response = await fetch("/api/bot/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    document.getElementById("botStatus").textContent = JSON.stringify(result, null, 2);
    if (!result.ok) throw new Error(result.error || "配置更新失败");
    setBotUiState(result.data.running ? "running" : "stopped", result.data.running ? "参数已应用" : "参数已保存", "下一轮循环自动生效");
    setTimeout(refreshBotStatus, 1000);
  } catch (error) {
    renderBotError(error);
  }
}

async function loadBeatConfig() {
  try {
    setBotUiState("starting", "载入中", "正在读取 BEAT 配置");
    const response = await fetch("/api/bot/config", { cache: "no-store" });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "读取 BEAT 配置失败");
    applyConfigToBotForm("beat", { ...botDefaults.beat, ...(result.data || {}) });
    saveBotForm("beat");
    syncMonitorFromBotForm("beat");
    setBotUiState("stopped", "BEAT参数已载入", "现在可以应用或启动 BEAT");
    await refreshBotStatus();
  } catch (error) {
    renderBotError(error);
  }
}

async function loadReBotConfig() {
  try {
    setReBotUiState("starting", "载入中", "正在读取 RE 独立配置");
    const response = await fetch("/api/re-bot/config", { cache: "no-store" });
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "读取 RE 配置失败");
    applyConfigToBotForm("re", { ...botDefaults.re, ...(result.data || {}) });
    saveBotForm("re");
    syncMonitorFromBotForm("re");
    setReBotUiState("stopped", "RE参数已载入", "现在可以干跑或启动 RE 机器人");
    await refreshReBotStatus();
  } catch (error) {
    renderReBotError(error);
  }
}

async function dryRunReBotOnce() {
  try {
    saveBotForm("re");
    const payload = buildBotPayload("re");
    payload.live = false;
    payload.setLeverage = false;
    setReBotUiState("starting", "RE干跑中", "只预演一轮，不会实盘下单");
    setReBotButtons(false, true);
    const response = await fetch("/api/re-bot/dry-run-once", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    renderReBotStatus(result);
    if (!result.ok) throw new Error(result.error || "RE 干跑失败");
    setTimeout(refreshReBotStatus, 1000);
  } catch (error) {
    renderReBotError(error);
  }
}

async function startReBot() {
  try {
    saveBotForm("re");
    const payload = buildBotPayload("re");
    setReBotUiState("starting", "RE启动中", payload.live ? "正在启动 RE 实盘机器人" : "正在启动 RE dry-run 机器人");
    setReBotButtons(false, true);
    const response = await fetch("/api/re-bot/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    renderReBotStatus(result);
    if (result.ok) setTimeout(refreshReBotStatus, 1200);
  } catch (error) {
    renderReBotError(error);
  }
}

async function stopReBot() {
  setReBotUiState("stopping", "RE停止中", "正在结束 RE 机器人进程");
  try {
    setReBotButtons(true, true);
    const response = await fetch("/api/re-bot/stop", { method: "POST" });
    const result = await response.json();
    renderReBotStatus(result);
  } catch (error) {
    renderReBotError(error);
  }
}

async function updateReBotConfig() {
  try {
    saveBotForm("re");
    const payload = buildBotPayload("re");
    setReBotUiState("starting", "RE应用中", "正在热更新 RE 参数");
    const response = await fetch("/api/re-bot/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    document.getElementById("reBotStatus").textContent = JSON.stringify(result, null, 2);
    if (!result.ok) throw new Error(result.error || "RE 配置更新失败");
    setReBotUiState(result.data.running ? "running" : "stopped", result.data.running ? "RE参数已应用" : "RE参数已保存", "下一轮循环自动生效");
    setTimeout(refreshReBotStatus, 1000);
  } catch (error) {
    renderReBotError(error);
  }
}

async function refreshBotStatus() {
  try {
    const response = await fetch("/api/bot/status", { cache: "no-store" });
    const result = await response.json();
    latestBot = result;
    renderBotStatus(result);
    if (latestData) {
      renderRuntimeSummary(latestData, activeBotResult(latestData));
      drawChart(latestData);
    }
  } catch (error) {
    renderBotError(error);
  }
}

async function refreshReBotStatus() {
  try {
    const response = await fetch("/api/re-bot/status", { cache: "no-store" });
    const result = await response.json();
    latestReBot = result;
    renderReBotStatus(result);
    if (latestData) {
      renderRuntimeSummary(latestData, activeBotResult(latestData));
      drawChart(latestData);
    }
  } catch (error) {
    renderReBotError(error);
  }
}

function buildBotPayload(bot = "beat") {
  const form = readBotForm(bot);
  return {
    ...botDefaults[bot],
    ...form,
    live: form.live,
    setLeverage: form.setLeverage,
    cancelOnStop: form.cancelOnStop,
    exchangeStopEnabled: form.exchangeStopEnabled,
    recenterOnCooldown: form.recenterOnCooldown,
    oneWayOpen: form.oneWayOpen,
  };
}

function readBotForm(bot) {
  const get = (suffix) => document.getElementById(`${bot}${suffix}`);
  const data = { ...botDefaults[bot] };
  Object.entries(botFieldMap).forEach(([key, suffix]) => {
    const el = get(suffix);
    if (el) data[key] = el.value;
  });
  data.live = get("BotLive")?.value === "true";
  data.setLeverage = Boolean(get("SetLeverage")?.checked);
  data.cancelOnStop = Boolean(get("CancelOnStop")?.checked);
  data.exchangeStopEnabled = Boolean(get("ExchangeStopEnabled")?.checked);
  data.recenterOnCooldown = Boolean(get("RecenterOnCooldown")?.checked);
  data.oneWayOpen = Boolean(get("OneWayOpen")?.checked);
  data.confirmLive = get("ConfirmLive")?.value || "";
  return data;
}

function applyConfigToBotForm(bot, config) {
  const get = (suffix) => document.getElementById(`${bot}${suffix}`);
  Object.entries(botFieldMap).forEach(([key, suffix]) => {
    const el = get(suffix);
    if (el && config[key] !== undefined && config[key] !== null) el.value = String(config[key]);
  });
  const live = get("BotLive");
  if (live && config.live !== undefined) live.value = String(Boolean(config.live));
  const checkboxes = {
    SetLeverage: "setLeverage",
    CancelOnStop: "cancelOnStop",
    ExchangeStopEnabled: "exchangeStopEnabled",
    RecenterOnCooldown: "recenterOnCooldown",
    OneWayOpen: "oneWayOpen",
  };
  Object.entries(checkboxes).forEach(([suffix, key]) => {
    const el = get(suffix);
    if (el && config[key] !== undefined) el.checked = Boolean(config[key]);
  });
}

function activeBotResult(data = latestData) {
  const instId = data?.params?.instId || document.getElementById("instId")?.value;
  return instId === "RE-USDT-SWAP" ? latestReBot : latestBot;
}

function renderBotStatus(result) {
  const box = document.getElementById("botStatus");
  if (!result.ok) {
    setBotUiState("error", "启动失败", result.error || "机器人接口返回错误");
    setBotButtons(false, false);
    box.textContent = JSON.stringify(result, null, 2);
    if (String(result.error || "").includes("already running")) {
      setTimeout(refreshBotStatus, 800);
    }
    return;
  }
  const data = result.data;
  const summary = data.diagnostics?.summary;
  if (data.running) {
    setBotUiState(summary?.level || "running", summary?.label || "运行中", summary?.detail || `PID ${data.pid || "--"} · ${commandSummary(data.command)}`);
  } else if (data.returnCode && data.returnCode !== 0) {
    setBotUiState("error", "异常退出", `退出码 ${data.returnCode}`);
  } else {
    setBotUiState("stopped", "未运行", data.startedAt ? "机器人已停止" : "等待启动");
  }
  setBotButtons(data.running, false);
  box.textContent = [
    `running=${data.running}`,
    `pid=${data.pid || "--"}`,
    `startedAt=${data.startedAt || "--"}`,
    `runtimeConfig=${JSON.stringify(data.runtimeConfig || {})}`,
    `log=${data.logPath}`,
    "",
    data.logTail || "暂无日志",
  ].join("\n");
}

function renderBotError(error) {
  const message = String(error);
  setBotUiState("error", "操作失败", message);
  setBotButtons(false, false);
  document.getElementById("botStatus").textContent = message;
}

function renderReBotStatus(result) {
  const box = document.getElementById("reBotStatus");
  if (!result.ok) {
    setReBotUiState("error", "RE操作失败", result.error || "RE 机器人接口返回错误");
    setReBotButtons(false, false);
    box.textContent = JSON.stringify(result, null, 2);
    return;
  }
  const data = result.data;
  const summary = data.diagnostics?.summary;
  if (data.mode === "dry-run-once" && data.returnCode === 0) {
    setReBotUiState("stopped", "RE干跑完成", "查看下方日志确认计划挂单");
  } else if (data.running) {
    setReBotUiState(summary?.level || "running", summary?.label || "RE运行中", summary?.detail || `PID ${data.pid || "--"} · ${commandSummary(data.command)}`);
  } else if (data.returnCode && data.returnCode !== 0) {
    setReBotUiState("error", "RE异常退出", `退出码 ${data.returnCode}`);
  } else {
    setReBotUiState("stopped", "RE未运行", data.startedAt ? "RE 机器人已停止" : "等待启动");
  }
  setReBotButtons(data.running, false);
  box.textContent = [
    `running=${data.running}`,
    `pid=${data.pid || "--"}`,
    `startedAt=${data.startedAt || "--"}`,
    `botPrefix=${data.botPrefix || "--"}`,
    `runtimeConfig=${JSON.stringify(data.runtimeConfig || {})}`,
    `log=${data.logPath}`,
    "",
    data.logTail || "暂无日志",
  ].join("\n");
}

function renderReBotError(error) {
  const message = String(error);
  setReBotUiState("error", "RE操作失败", message);
  setReBotButtons(false, false);
  document.getElementById("reBotStatus").textContent = message;
}

function setBotUiState(level, label, detail) {
  const card = document.getElementById("botStateCard");
  card.className = `botStateCard ${level}`;
  text("botStateLabel", label);
  text("botStateDetail", detail);
}

function setReBotUiState(level, label, detail) {
  const card = document.getElementById("reBotStateCard");
  card.className = `botStateCard ${level}`;
  text("reBotStateLabel", label);
  text("reBotStateDetail", detail);
}

function setBotButtons(running, busy) {
  const start = document.getElementById("startBotBtn");
  const stop = document.getElementById("stopBotBtn");
  const update = document.getElementById("updateBotBtn");
  start.disabled = busy || running;
  stop.disabled = busy || !running;
  update.disabled = busy;
  start.textContent = busy && !running ? "启动中" : "启动";
  stop.textContent = busy && running ? "停止中" : "停止";
}

function setReBotButtons(running, busy) {
  const load = document.getElementById("loadReBotConfigBtn");
  const dryRun = document.getElementById("dryRunReBotBtn");
  const start = document.getElementById("startReBotBtn");
  const update = document.getElementById("updateReBotBtn");
  const stop = document.getElementById("stopReBotBtn");
  load.disabled = busy;
  dryRun.disabled = busy || running;
  start.disabled = busy || running;
  update.disabled = busy;
  stop.disabled = busy || !running;
  dryRun.textContent = busy && !running ? "RE干跑中" : "RE干跑一次";
  start.textContent = busy && !running ? "RE启动中" : "启动RE";
  stop.textContent = busy && running ? "RE停止中" : "停止RE";
}

function commandSummary(command) {
  if (!Array.isArray(command)) return "--";
  const pick = (flag) => {
    const index = command.indexOf(flag);
    return index >= 0 ? command[index + 1] : "";
  };
  const tradeMode = command.includes("--live") ? "live" : "dry-run";
  return [pick("--inst-id"), tradeMode, pick("--mode"), pick("--sizing-mode")].filter(Boolean).join(" · ");
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
  drawOrders(ctx, data.pendingOrders || [], y, left, w - right);
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

function drawOrders(ctx, orders, y, x1, x2) {
  const prefix = latestData?.params?.instId === "RE-USDT-SWAP" ? "gr" : "gb";
  const botOrders = (orders || []).filter((order) => String(order.clOrdId || "").startsWith(prefix));
  botOrders.forEach((order, index) => {
    const price = Number(order.px);
    if (!Number.isFinite(price)) return;
    const isClose = String(order.reduceOnly).toLowerCase() === "true";
    const color = isClose ? "#2563eb" : order.posSide === "long" ? "#16817a" : "#b7791f";
    const px = x2 - 18 - (index % 8) * 10;
    const py = y(price);
    ctx.save();
    ctx.fillStyle = color;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(px, py, isClose ? 5 : 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  });
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

function time(ms) {
  const num = Number(ms);
  return Number.isFinite(num) ? new Date(num).toLocaleTimeString() : "--";
}
