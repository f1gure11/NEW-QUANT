const ETH_DEFAULTS = {
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
  exchangeStopEnabled: true,
};

let latestPortfolio = null;
let latestSnapshot = null;

async function refresh() {
  const failures = [];
  try {
    setConn("连接中", "watch");
    const [portfolioResult] = await Promise.allSettled([getJson("/api/portfolio/latest?includeAccount=1&includeRegimeResearch=1")]);
    if (portfolioResult.status === "fulfilled") {
      latestPortfolio = portfolioResult.value.data || {};
    } else {
      failures.push(`组合数据：${portfolioResult.reason?.message || portfolioResult.reason}`);
      latestPortfolio = latestPortfolio || {};
    }

    safeRender("组合", () => renderPortfolio(latestPortfolio), failures);

    const bot = activeEthBot();
    latestSnapshot = portfolioSnapshot(bot);

    safeRender("快照", () => renderSnapshot(latestSnapshot), failures);
    safeRender("ETH状态", () => renderEth(bot, latestSnapshot), failures);
    if (failures.length) {
      setConn("部分连接", "warn");
      text("updatedAt", `${time(latestSnapshot.capturedAt)} · ${failures[0]}`);
    } else {
      setConn("已连接", "ok");
    }
  } catch (error) {
    console.error(error);
    setConn("连接失败", "danger");
    text("updatedAt", String(error?.message || error));
    safeRender("组合", () => renderPortfolio(latestPortfolio || {}));
    safeRender("ETH状态", () => renderEth(activeEthBot(), latestSnapshot || portfolioSnapshot(activeEthBot())));
  }
}

function portfolioSnapshot(bot) {
  const params = { ...ETH_DEFAULTS, ...(bot?.runtimeConfig || {}) };
  const cycle = bot?.diagnostics?.cycle || {};
  const account = latestPortfolio?.account || {};
  return {
    capturedAt: account.capturedAt || new Date().toISOString(),
    params,
    account: account.account || {},
    balance: account.balance || latestPortfolio?.live?.balance || {},
    pnl: account.pnl || latestPortfolio?.live?.pnl || latestPortfolio?.latestReport?.live?.pnl || {},
    trading: { liveEnabled: Boolean(latestPortfolio?.live?.enabled || latestPortfolio?.latestReport?.live?.enabled) },
    market: { ticker: { last: cycle.last || params.last || "" } },
    pendingOrders: [],
    fills: [],
    positions: [],
  };
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error || `${path} failed`);
  return payload;
}

function safeRender(label, renderFn, failures = null) {
  try {
    return renderFn();
  } catch (error) {
    console.error(`${label} render failed`, error);
    if (failures) failures.push(`${label}渲染：${error?.message || error}`);
    return undefined;
  }
}

function renderSnapshot(data) {
  text("updatedAt", time(data.capturedAt));
  text("totalEq", money(data.balance?.totalEq));
  const usdt = (data.balance?.details || []).find((item) => item.ccy === "USDT");
  text("usdtAvail", money(usdt?.availBal));
  text("accountDetail", `USDT 权益 ${money(usdt?.eq)} · 未实现 ${signed(data.pnl?.unrealized, 4)}`);
  text("accountMode", `${data.account?.posMode || "--"} · ${data.account?.perm || "--"}`);

  const dailyPnlValue = Number(data.pnl?.recent24h || 0);
  text("dailyPnl", signed(dailyPnlValue, 6));
  text("dailyPnlDetail", `最近24h成交净额 · ${data.pnl?.recent24hFillCount ?? 0} 笔`);
  colorSigned("dailyPnl", dailyPnlValue);

  const pnlValue = Number(data.pnl?.estimatedTotal || 0);
  text("ethPnl", signed(pnlValue, 6));
  text("totalPnlDetail", `成交+手续费+未实现 · 5h ${signed(data.pnl?.recent5h, 6)} / ${data.pnl?.recent5hFillCount ?? 0} 笔`);
  colorSigned("ethPnl", pnlValue);

  const liveEnabled = Boolean(data.trading?.liveEnabled);
  text("liveEnabled", liveEnabled ? "开启" : "关闭");
  document.getElementById("liveSwitch")?.classList.toggle("on", liveEnabled);

  renderFills(data.fills || []);
}

function renderEth(bot, snapshotData) {
  const diagnostics = bot?.diagnostics || {};
  const summary = diagnostics.summary || {};
  const rolling = diagnostics.rollingAdaptive || {};
  const sizing = diagnostics.sizing || {};
  const edge = diagnostics.edge || {};
  const cycle = diagnostics.cycle || {};
  const openGuard = diagnostics.openGuard || {};
  const strategy = snapshotData?.strategy || {};
  const running = Boolean(bot?.running);
  const stateLevel = running ? summary.level || "ok" : "stopped";
  const stateLabel = summary.label || (running ? "运行中" : "未运行");
  const title = bot?.source === "portfolio" ? "组合 ETH 实盘" : "ETH 实盘状态";

  setPill("ethState", stateLabel, stateLevel);
  setDot("ethStatusDot", stateLevel);
  text("ethPanelTitle", title);
  text("ethDigestLabel", title);
  text("ethPnlLabel", `${bot?.instId || "ETH"} 估算 PnL`);
  text("ethDigest", running ? `运行中 · ${bot?.botPrefix || "--"}` : "未运行");

  const liveLast = firstValue(cycle.last, snapshotData?.market?.ticker?.last);
  const lower = firstValue(cycle.lower, strategy.effectiveLower, snapshotData?.params?.lower);
  const upper = firstValue(cycle.upper, strategy.effectiveUpper, snapshotData?.params?.upper);
  text("ethLast", fmt(liveLast, priceDigits(liveLast)));
  text("ethLower", fmt(lower, priceDigits(lower)));
  text("ethUpper", fmt(upper, priceDigits(upper)));
  renderPriceRange(liveLast, lower, upper);

  const leverage = firstValue(rolling.leverage, snapshotData?.params?.leverage, bot?.runtimeConfig?.leverage);
  const gridBps = firstValue(rolling.gridBps, snapshotData?.params?.gridBps, bot?.runtimeConfig?.gridBps);
  const edgeText = edgeSummary(edge, strategy);
  text("ethLeverageGrid", `${fmt(leverage, 0)}x / ${fmt(gridBps, 2)} bps`);
  text("ethPosition", `L ${fmt(firstValue(cycle.long, positionSize(snapshotData, "long")), 4)} / S ${fmt(firstValue(cycle.short, positionSize(snapshotData, "short")), 4)}`);
  renderPositionBars(firstValue(cycle.long, positionSize(snapshotData, "long")), firstValue(cycle.short, positionSize(snapshotData, "short")));
  text("ethEdge", edgeText);
  text("ethOpenSides", openSides(openGuard, strategy.trend));

  const detail = `${fmt(leverage, 0)}x · ${fmt(gridBps, 2)}bps · ${edgeText}`;
  text("ethDetailDigest", rolling.leverage || strategy.minNetBps ? detail : summary.detail || "--");

  const decision = translateBotMessage(diagnostics.lastError?.text || diagnostics.lastDecision || summary.detail || strategy.state?.action || "--");
  const decisionEl = document.getElementById("ethDecision");
  if (decisionEl) {
    decisionEl.textContent = decision;
    decisionEl.classList.toggle("ok", !/过低|不足|止损|风控|冷静|错误|暂停|限制|不下单/i.test(decision));
  }

  renderEthAdaptive(rolling, sizing, strategy, bot?.runtimeConfig || {});
}

function renderPriceRange(last, lower, upper) {
  const low = Number(lower);
  const high = Number(upper);
  const price = Number(last);
  const pct = Number.isFinite(low) && Number.isFinite(high) && high > low && Number.isFinite(price)
    ? clamp(((price - low) / (high - low)) * 100, 0, 100)
    : 0;
  setStyle("ethRangeFill", "width", `${pct}%`);
  setStyle("ethRangeMarker", "left", `${pct}%`);
}

function renderPositionBars(longValue, shortValue) {
  const long = Math.abs(Number(longValue || 0));
  const short = Math.abs(Number(shortValue || 0));
  const max = Math.max(long, short, 0.0000001);
  setStyle("longBar", "width", `${clamp((long / max) * 100, 0, 100)}%`);
  setStyle("shortBar", "width", `${clamp((short / max) * 100, 0, 100)}%`);
}

function renderEthAdaptive(rolling, sizing, strategy, runtimeConfig) {
  html(
    "ethAdaptiveTable",
    table(
      [
        { label: "参数", type: "text" },
        { label: "当前值", type: "num" },
      ],
      [
        ["杠杆", `${fmt(firstValue(rolling.leverage, runtimeConfig.leverage, strategy.params?.leverage), 0)}x`],
        ["格距", `${fmt(firstValue(rolling.gridBps, runtimeConfig.gridBps, strategy.params?.targetGridBps), 2)} bps`],
        ["每单保证金", pctValue(firstValue(rolling.orderMarginPct, runtimeConfig.orderMarginPct, strategy.sizing?.orderMarginPct), 2)],
        ["单边保证金上限", pctValue(firstValue(rolling.maxMarginPct, runtimeConfig.maxMarginPct, strategy.sizing?.maxMarginPct), 2)],
        ["单笔止盈", `${fmt(firstValue(rolling.minTpBps, runtimeConfig.minTpBps, strategy.risk?.minTpBps), 2)} bps`],
        ["单仓止损", `${fmt(firstValue(rolling.positionLossSlBps, runtimeConfig.positionLossSlBps, strategy.risk?.positionLossSlBps), 2)} bps`],
        ["交易所保护止损", `${fmt(firstValue(rolling.exchangeStopBps, runtimeConfig.exchangeStopBps, strategy.risk?.exchangeStop?.bps), 2)} bps`],
        ["总收益/总止损", `${pctValue(firstValue(rolling.totalProfitTpPct, runtimeConfig.totalProfitTpPct), 2)} / ${pctValue(firstValue(rolling.totalLossSlPct, runtimeConfig.totalLossSlPct), 2)}`],
        ["风险分", fmt(firstValue(rolling.riskScore, runtimeConfig.poolAdaptiveRiskScore), 3)],
        [
          "窗口波动",
          `${fmt(firstValue(rolling.avgAbsBps, runtimeConfig.poolAvgAbsBps), 2)} / shock ${fmt(
            firstValue(rolling.shockBps, runtimeConfig.poolShockBps),
            2,
          )} bps`,
        ],
        ["可用基准", `${fmt(firstValue(sizing.basis, strategy.sizing?.basisMargin), 4)} USDT`],
        ["策略状态", `${strategy.state?.label || "--"} · ${strategy.state?.action || "--"}`],
      ],
    ),
  );
}

function renderPortfolio(data) {
  const report = data?.latestReport;
  if (!report) {
    renderPortfolioEmpty();
    renderBacktestStatus(data?.backtest || {});
    return;
  }
  const summary = report.summary || {};
  const live = data?.live || report.live || {};
  const targets = report.rebalance?.targets || [];
  const actions = report.rebalance?.actions || [];
  const allocation = report.rebalance?.allocation || {};
  const adaptiveRows = summary.adaptivePreview || [];
  const coreRows = targets.filter((target) => target.role === "core");
  const satelliteRows = targets.filter((target) => target.role === "satellite");
  const coreWeight = roleWeightPct(targets, "core");
  const satelliteWeight = roleWeightPct(targets, "satellite");

  text("coreDigest", `${coreRows.length} 个`);
  text("coreDetail", `权重 ${fmt(coreWeight, 2)}% · ${report.generatedAt || "--"}`);
  text("satelliteDigest", `${satelliteRows.length} 个`);
  text("satelliteDetail", `权重 ${fmt(satelliteWeight, 2)}% · 上限 ${fmt(allocation.satellite_max_weight_pct, 2)}%`);
  text("rebalanceDigest", rebalanceTimingText(actions, allocation));
  text("rebalanceDetail", actionMix(summary.actionsByType));
  text("adaptiveDigest", adaptiveProfileText(adaptiveRows));
  text("adaptiveDetail", `${modeText(summary.tradingMode)} · 实盘 ${summary.liveRunningCount ?? live.runningCount ?? 0}/${summary.liveTargetCount ?? live.targetCount ?? 0} · 预检 ${live.preflightStatus || report.preflight?.status || "--"}`);

  renderRoleTargets(coreRows, report.scores || [], report.runtimeConfigs || [], "coreDetails", "核心舱", "coreSummary", report.eligibilityDiagnostics || []);
  renderRoleTargets(satelliteRows, report.scores || [], report.runtimeConfigs || [], "satelliteDetails", "卫星仓", "satelliteSummary", report.eligibilityDiagnostics || []);
  renderRebalanceTiming(actions, allocation);
  renderBacktestStatus(data.backtest || {});
  renderRebalanceRecords(actions, report.generatedAt, allocation);
  renderPortfolioAdaptive(adaptiveRows);
  renderRegimeResearch(data?.regimeResearch, report.runtimeConfigs || []);
}

function renderPortfolioEmpty() {
  [
    "coreDigest",
    "coreDetail",
    "satelliteDigest",
    "satelliteDetail",
    "rebalanceDigest",
    "rebalanceDetail",
    "adaptiveDigest",
    "adaptiveDetail",
    "coreSummary",
    "satelliteSummary",
    "rebalanceSummary",
    "backtestSummary",
    "rebalanceRecordSummary",
    "adaptiveSummary",
    "regimeResearchSummary",
  ].forEach((id) =>
    text(id, "--"),
  );
  ["coreDetails", "satelliteDetails", "rebalanceLogic", "backtestDetail", "rebalanceRecords", "portfolioAdaptive", "regimeResearch"].forEach((id) =>
    html(id, '<div class="empty">暂无组合报告</div>'),
  );
}

function renderBacktestStatus(backtest) {
  const state = backtest.running ? "running" : backtest.state || (backtest.returnCode === 0 ? "completed" : backtest.returnCode == null ? "idle" : "failed");
  text("backtestSummary", `${backtestStateText(state)} · 日志 ${time(backtest.lastLogAt)}`);
  html(
    "backtestDetail",
    table(
      [
        { label: "项目", type: "text" },
        { label: "值", type: "text" },
      ],
      [
        ["状态", backtestStateText(state)],
        ["PID", backtest.pid || "--"],
        ["启动时间", time(backtest.startedAt)],
        ["最新日志", time(backtest.lastLogAt)],
        ["最新报告", time(backtest.lastReportAt)],
        ["报告目录", backtest.lastReportDir || backtest.latestReportPath || "--"],
      ],
    ),
  );
}

function renderRebalanceRecords(actions, generatedAt, allocation) {
  text("rebalanceRecordSummary", actions.length ? `${actions.length} 条 · ${time(generatedAt)}` : "--");
  if (!actions.length) {
    html("rebalanceRecords", '<div class="empty">暂无调仓记录</div>');
    return;
  }
  html(
    "rebalanceRecords",
    table(
      [
        { label: "时间", type: "text" },
        { label: "动作", type: "text" },
        { label: "合约", type: "text" },
        { label: "当前/目标", type: "num" },
        { label: "差值", type: "num" },
        { label: "原因", type: "text" },
      ],
      actions.map((action) => [
        time(action.generated_at || generatedAt),
        actionText(action.action),
        action.inst_id,
        `${fmt(action.current_weight_pct, 2)}% / ${fmt(action.target_weight_pct, 2)}%`,
        `${Number(action.delta_weight_pct || 0) >= 0 ? "+" : ""}${fmt(action.delta_weight_pct, 2)}%`,
        action.reason || reasonText(action.note, allocation),
      ]),
    ),
  );
}

function renderRoleTargets(targets, scores, runtimeConfigs, targetId, label, summaryId, diagnostics = []) {
  const scoreByInst = Object.fromEntries(scores.map((row) => [row.inst_id, row]));
  const runtimeByInst = Object.fromEntries(runtimeConfigs.map((row) => [row.instId, row]));
  const totalWeight = targets.reduce((sum, item) => sum + Number(item.weight_pct || 0), 0);
  text(summaryId, `${targets.length} 个${label} · 合计 ${fmt(totalWeight, 2)}%`);
  if (!targets.length) {
    html(targetId, emptyTargetHtml(label, diagnostics));
    return;
  }
  html(
    targetId,
    `<div class="satelliteGrid">${targets
      .map((target) => {
        const score = scoreByInst[target.inst_id] || {};
        const runtime = runtimeByInst[target.inst_id] || {};
        return `<section class="satelliteItem">
          <div class="satelliteItemHead">
            <h3>${esc(target.inst_id)}</h3>
            ${badge(`权重 ${fmt(target.weight_pct, 2)}%`, "ok")}
          </div>
          <dl>
            ${metric("排名", target.rank)}
            ${metric("目标保证金", fmt(target.target_margin, 4))}
            ${metric("每单/上限", `${target.order_sz || "--"} / ${target.max_position || "--"}`)}
            ${metric("格距", `${fmt(runtime.gridBps, 2)} bps`)}
            ${metric("杠杆", `${fmt(runtime.leverage, 0)}x`)}
            ${metric("单笔TP", `${fmt(runtime.minTpBps, 2)} bps`)}
            ${metric("回测收益", `${fmt(score.total_return_pct, 2)}%`)}
            ${metric("成交", score.fills || "--")}
          </dl>
        </section>`;
      })
      .join("")}</div>`,
  );
}

function emptyTargetHtml(label, diagnostics) {
  const filtered = (diagnostics || []).filter((item) => item.status === "filtered").slice(0, 6);
  if (!filtered.length) return `<div class="empty">暂无${label}</div>`;
  return [
    `<div class="empty">暂无${label}：候选未通过组合过滤</div>`,
    table(
      [
        { label: "排名", type: "num" },
        { label: "合约", type: "text" },
        { label: "收益", type: "num" },
        { label: "风险事件", type: "num" },
        { label: "过滤原因", type: "text" },
      ],
      filtered.map((item) => [
        item.rank,
        item.instId,
        `${fmt(item.totalReturnPct, 2)}%`,
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

function renderRebalanceTiming(actions, allocation) {
  text("rebalanceSummary", rebalanceSummary(actions, allocation));
  if (!actions.length) {
    html("rebalanceLogic", '<div class="empty">暂无调仓逻辑</div>');
    return;
  }
  html(
    "rebalanceLogic",
    `<div class="logicList">${actions
      .map((action) => {
        const delta = Number(action.delta_weight_pct || 0);
        const level = action.action === "enter" || action.action === "increase" ? "ok" : action.action === "decrease" || action.action === "exit" ? "warn" : "";
        return `<section class="logicItem">
          <div class="logicItemHead">
            <h3>${esc(action.inst_id)}</h3>
            <strong>${esc(actionText(action.action))} ${delta >= 0 ? "+" : ""}${fmt(delta, 2)}%</strong>
          </div>
          <div class="logicFlow">
            ${logicMetric("当前权重", `${fmt(action.current_weight_pct, 2)}%`)}
            <span class="logicArrow">→</span>
            ${logicMetric("目标权重", `${fmt(action.target_weight_pct, 2)}%`)}
            <span class="logicArrow">=</span>
            ${logicMetric("调仓差值", `${delta >= 0 ? "+" : ""}${fmt(delta, 2)}%`)}
          </div>
          <p class="logicReason">
            ${badge(actionText(action.action), level)}
            偏离达到 ${fmt(allocation.rebalance_threshold_pct, 2)}% 阈值时调仓。
            ${esc(reasonText(action.note))}
          </p>
        </section>`;
      })
      .join("")}</div>`,
  );
}

function renderPortfolioAdaptive(rows) {
  text("adaptiveSummary", adaptiveProfileText(rows));
  if (!rows.length) {
    html("portfolioAdaptive", '<div class="empty">暂无自适应参数</div>');
    return;
  }
  html(
    "portfolioAdaptive",
    table(
      [
        { label: "角色", type: "text" },
        { label: "合约", type: "text" },
        { label: "杠杆", type: "num" },
        { label: "格距", type: "num" },
        { label: "单笔TP", type: "num" },
        { label: "总TP/SL", type: "num" },
        { label: "单仓/交易所SL", type: "num" },
        { label: "风险/趋势", type: "text" },
        { label: "池波动", type: "num" },
      ],
      rows.map((row) => [
        roleText(row.role),
        row.instId,
        row.leverage ? `${fmt(row.leverage, 0)}x` : "--",
        `${fmt(row.gridBps, 2)} bps`,
        `${fmt(row.minTpBps, 2)} bps`,
        `${fmt(row.totalProfitTpPct, 2)}% / ${fmt(row.totalLossSlPct, 2)}%`,
        `${fmt(row.positionLossSlBps, 0)} / ${fmt(row.exchangeStopBps, 0)} bps`,
        `${fmt(row.riskScore, 3)} · ${trendLabel(row.trendFilter)}`,
        `${fmt(row.poolAvgAbsBps, 2)} / ${fmt(row.poolShockBps, 2)} bps`,
      ]),
    ),
  );
}

function renderRegimeResearch(research, runtimeConfigs = []) {
  if (!research) {
    text("regimeResearchSummary", "--");
    html("regimeResearch", '<div class="empty">暂无状态模型报告</div>');
    return;
  }
  const best = research.bestVariant || {};
  const activeModes = [...new Set(runtimeConfigs.map((item) => item.marketRegimeFilter || "off"))].join(", ") || "off";
  const mixedPolicy = mixedPolicyText(runtimeConfigs[0]?.marketRegimeMixedPolicy);
  text(
    "regimeResearchSummary",
    `${research.name || "--"} · 最佳研究层 ${regimeVariantText(best.variant)} · 当前 ${activeModes} · ${mixedPolicy}`,
  );
  const variantRows = (research.variantSummary || []).map((row) => [
    regimeVariantText(row.variant),
    row.symbols,
    `${fmt(row.avgReturnPct, 2)}%`,
    `${fmt(row.avgMaxDrawdownPct, 2)}%`,
    fmt(row.avgScore, 2),
    row.totalRiskEvents,
  ]);
  const topRows = (research.topRows || [])
    .filter((row) => row.variant === best.variant)
    .slice(0, 6)
    .map((row) => [
      row.instId,
      `${fmt(row.totalReturnPct, 2)}%`,
      `${fmt(row.maxDrawdownPct, 2)}%`,
      row.fills,
      row.riskEvents,
      `${regimeSignalText(row.latestSignal)} ${fmt(row.latestConfidence, 2)}`,
    ]);
  html(
    "regimeResearch",
    [
      table(
        [
          { label: "项目", type: "text" },
          { label: "值", type: "text" },
        ],
        [
          ["报告", `${research.generatedAt || "--"} · ${research.reportDir || "--"}`],
          ["当前实盘开关", `${activeModes} · ${mixedPolicy}`],
          ["相对基线", `收益 ${signed(best.returnDeltaVsBaseline, 2)}%，回撤 ${signed(best.drawdownDeltaVsBaseline, 2)}%，风险事件 ${signed(best.riskEventDeltaVsBaseline, 0)}`],
          ["RF/HMM 弱标签", `${fmt(research.models?.rf?.accuracy, 3)} / ${fmt(research.models?.hmm?.accuracyVsWeakLabels, 3)}`],
          ["QuantDinger", `${research.quantDinger?.license || "--"} · 标准已参考，未接管实盘执行`],
        ],
      ),
      variantRows.length
        ? table(
            [
              { label: "方案", type: "text" },
              { label: "标的", type: "num" },
              { label: "均收益", type: "num" },
              { label: "均回撤", type: "num" },
              { label: "均分", type: "num" },
              { label: "风险", type: "num" },
            ],
            variantRows,
          )
        : "",
      topRows.length
        ? table(
            [
              { label: "合约", type: "text" },
              { label: "收益", type: "num" },
              { label: "回撤", type: "num" },
              { label: "成交", type: "num" },
              { label: "风险", type: "num" },
              { label: "最新", type: "text" },
            ],
            topRows,
          )
        : "",
    ].join(""),
  );
}

function renderSatellites(targets, scores, runtimeConfigs) {
  const satellites = targets.filter((target) => target.role === "satellite");
  const scoreByInst = Object.fromEntries(scores.map((row) => [row.inst_id, row]));
  const runtimeByInst = Object.fromEntries(runtimeConfigs.map((row) => [row.instId, row]));
  const totalWeight = satellites.reduce((sum, item) => sum + Number(item.weight_pct || 0), 0);
  text("satelliteSummary", `${satellites.length} 个卫星目标 · 合计 ${fmt(totalWeight, 2)}% · 单个权重上限来自组合配置`);

  if (!satellites.length) {
    html("satelliteDetails", '<div class="empty">暂无卫星仓</div>');
    return;
  }

  html(
    "satelliteDetails",
    `<div class="satelliteGrid">${satellites
      .map((target) => {
        const score = scoreByInst[target.inst_id] || {};
        const runtime = runtimeByInst[target.inst_id] || {};
        return `<section class="satelliteItem">
          <div class="satelliteItemHead">
            <h3>${esc(target.inst_id)}</h3>
            ${badge(`权重 ${fmt(target.weight_pct, 2)}%`, "ok")}
          </div>
          <dl>
            ${metric("排名", target.rank)}
            ${metric("目标保证金", fmt(target.target_margin, 4))}
            ${metric("每单/上限", `${target.order_sz || "--"} / ${target.max_position || "--"}`)}
            ${metric("回测收益", `${fmt(score.total_return_pct, 2)}%`)}
            ${metric("最大回撤", `${fmt(score.max_drawdown_pct, 2)}%`)}
            ${metric("胜率", `${fmt(score.win_rate_pct, 2)}%`)}
            ${metric("PF", fmt(score.profit_factor, 2))}
            ${metric("成交", score.fills || "--")}
            ${metric("杠杆", `${fmt(runtime.leverage, 0)}x`)}
            ${metric("格距", `${fmt(runtime.gridBps, 2)} bps`)}
            ${metric("单笔TP", `${fmt(runtime.minTpBps, 2)} bps`)}
            ${metric("总TP/SL", `${fmt(runtime.totalProfitTpPct, 2)}% / ${fmt(runtime.totalLossSlPct, 2)}%`)}
            ${metric("单边/交易所SL", `${fmt(runtime.positionLossSlBps, 0)} / ${fmt(runtime.exchangeStopBps, 0)} bps`)}
            ${metric("回测风控", `${fmt(runtime.backtestRiskRewardScore, 3)} · ret ${fmt(runtime.backtestTotalReturnPct, 2)} / dd ${fmt(runtime.backtestMaxDrawdownPct, 2)}`)}
            ${metric("风险/趋势", `${fmt(runtime.poolAdaptiveRiskScore, 3)} · ${trendLabel(runtime.trendFilter)}`)}
            ${metric("趋势分差", signed(runtime.trendScoreDelta, 2))}
          </dl>
        </section>`;
      })
      .join("")}</div>`,
  );
}

function renderRebalanceLogic(actions, exposures, intents) {
  text("rebalanceSummary", rebalanceSummary(actions));
  if (!actions.length) {
    html("rebalanceLogic", '<div class="empty">暂无调仓逻辑</div>');
    return;
  }
  const exposureByInst = Object.fromEntries(exposures.map((item) => [item.inst_id, item]));
  const intentByInst = Object.fromEntries(intents.map((item) => [item.inst_id, item]));
  html(
    "rebalanceLogic",
    `<div class="logicList">${actions
      .map((action) => {
        const exposure = exposureByInst[action.inst_id] || {};
        const intent = intentByInst[action.inst_id] || {};
        const delta = Number(action.delta_weight_pct || 0);
        const level = action.action === "enter" || action.action === "increase" ? "ok" : action.action === "decrease" || action.action === "exit" ? "warn" : "";
        return `<section class="logicItem">
          <div class="logicItemHead">
            <h3>${esc(action.inst_id)}</h3>
            <strong>${esc(actionText(action.action))} ${delta >= 0 ? "+" : ""}${fmt(delta, 2)}%</strong>
          </div>
          <div class="logicFlow">
            ${logicMetric("当前权重", `${fmt(action.current_weight_pct, 2)}%`)}
            <span class="logicArrow">→</span>
            ${logicMetric("目标权重", `${fmt(action.target_weight_pct, 2)}%`)}
            <span class="logicArrow">=</span>
            ${logicMetric("调仓差值", `${delta >= 0 ? "+" : ""}${fmt(delta, 2)}%`)}
          </div>
          <p class="logicReason">
            ${badge(actionText(action.action), level)}
            当前保证金 ${fmt(action.current_margin, 4)}，目标保证金 ${fmt(action.target_margin, 4)}，差额 ${fmt(action.delta_margin, 4)}。
            ${esc(reasonText(action.note))}
            ${exposure.inst_id ? `现有暴露：多 ${fmt(exposure.long_sz, 4)} / 空 ${fmt(exposure.short_sz, 4)}，估算保证金 ${fmt(exposure.margin_estimate, 4)}。` : "当前账户没有该合约暴露。"}
            执行草案：${esc(statusText(intent.status))}。
          </p>
        </section>`;
      })
      .join("")}</div>`,
  );
}

function renderLiveCoverage(targets, intents, live) {
  const targetInsts = targets.map((item) => item.inst_id).filter(Boolean);
  const readyInsts = intents.filter((item) => item.status === "runtime_config_ready").map((item) => item.inst_id);
  const satelliteCount = targets.filter((item) => item.role === "satellite").length;
  const runningCount = live?.runningCount ?? 0;
  text(
    "liveCoverage",
    `组合报告包含 ${targetInsts.length} 个目标、${satelliteCount} 个卫星仓，已生成 ${readyInsts.length} 个组合滚动配置，当前组合实盘运行 ${runningCount} 个。ETH 已纳入组合 bot，不再使用旧独立 ETH 实盘。预检 ${live?.preflightStatus || "--"}，live plan ${live?.livePlanStatus || "--"}。此页面只读，不发起调仓或下单。`,
  );
}

function renderPortfolioLive(live) {
  const bots = live?.bots || [];
  text("portfolioLiveSummary", `${live?.enabled ? "实盘开关开启" : "实盘开关锁定"} · 运行 ${live?.runningCount ?? 0} / ${live?.targetCount ?? 0}`);
  if (!bots.length) {
    html("portfolioLiveTable", '<div class="empty">暂无组合实盘目标</div>');
    return;
  }
  html(
    "portfolioLiveTable",
    table(
      [
        { label: "合约", type: "text" },
        { label: "动作", type: "text" },
        { label: "状态", type: "text" },
        { label: "杠杆/格距", type: "num" },
        { label: "每单/上限", type: "num" },
        { label: "订单目标", type: "num" },
        { label: "总TP/SL", type: "num" },
        { label: "单笔TP/单仓SL", type: "num" },
        { label: "趋势", type: "text" },
        { label: "最近原因", type: "text" },
      ],
      bots.map((bot) => {
        const runtime = bot.runtimeConfig || {};
        const summary = bot.diagnostics?.summary || {};
        const sizing = bot.diagnostics?.sizing || {};
        const plan = bot.diagnostics?.orderPlan || {};
        return [
          bot.instId,
          actionText(bot.action),
          bot.running ? badge("实盘运行中", "ok") : badge("未运行", "warn"),
          `${fmt(runtime.leverage, 0)}x / ${fmt(runtime.gridBps, 2)} bps`,
          `${firstValue(sizing.orderSz, runtime.orderSz) ?? "--"} / ${firstValue(sizing.maxPosition, runtime.maxPosition) ?? "--"}`,
          `${plan.desired ?? "--"} / ${plan.existing ?? "--"} / ${plan.missing ?? "--"}`,
          `${fmt(runtime.totalProfitTpPct, 2)}% / ${fmt(runtime.totalLossSlPct, 2)}%`,
          `${fmt(runtime.minTpBps, 2)} / ${fmt(runtime.positionLossSlBps, 0)} bps`,
          trendLabel(runtime.trendFilter),
          translateBotMessage(bot.diagnostics?.lastError?.text || bot.diagnostics?.lastDecision || summary.detail || "--"),
        ];
      }),
      { rawColumns: [2] },
    ),
  );
}

function renderPaperPortfolio(intents) {
  const paper = intents.filter((intent) => intent.status === "runtime_config_ready" || intent.status === "rebalance_reduce_ready");
  text("paperPortfolioSummary", `${paper.length} 条沙盘/草案 · 只读展示，不执行`);
  if (!paper.length) {
    html("paperPortfolioTable", '<div class="empty">暂无沙盘草案</div>');
    return;
  }
  html(
    "paperPortfolioTable",
    table(
      [
        { label: "动作", type: "text" },
        { label: "合约", type: "text" },
        { label: "草案状态", type: "text" },
        { label: "配置", type: "text" },
      ],
      paper.map((intent) => [
        actionText(intent.action),
        intent.inst_id,
        badge(statusText(intent.status), intent.status === "runtime_config_ready" ? "ok" : "warn"),
        basename(intent.runtime_config_path),
      ]),
      { rawColumns: [2] },
    ),
  );
}

function renderScores(rows) {
  const okRows = rows.filter((row) => row.status === "ok").slice(0, 12);
  if (!okRows.length) {
    html("portfolioScores", '<div class="empty">暂无成功回测</div>');
    return;
  }
  html(
    "portfolioScores",
    table(
      [
        { label: "排名", type: "num" },
        { label: "合约", type: "text" },
        { label: "收益%", type: "num" },
        { label: "回撤%", type: "num" },
        { label: "胜率%", type: "num" },
        { label: "PF", type: "num" },
        { label: "成交", type: "num" },
        { label: "趋势", type: "text" },
      ],
      okRows.map((row) => [
        row.rank,
        row.inst_id,
        fmt(row.total_return_pct, 2),
        fmt(row.max_drawdown_pct, 2),
        fmt(row.win_rate_pct, 2),
        fmt(row.profit_factor, 2),
        row.fills,
        `${trendLabel(row.selected_trend_filter)} ${signed(row.trend_score_delta, 2)}`,
      ]),
    ),
  );
}

function renderTargets(targets) {
  if (!targets.length) {
    html("portfolioTargets", '<div class="empty">暂无目标仓位</div>');
    return;
  }
  html(
    "portfolioTargets",
    table(
      [
        { label: "角色", type: "text" },
        { label: "合约", type: "text" },
        { label: "权重%", type: "num" },
        { label: "保证金", type: "num" },
        { label: "每单", type: "num" },
        { label: "上限", type: "num" },
      ],
      targets.map((target) => [
        roleText(target.role),
        target.inst_id,
        fmt(target.weight_pct, 2),
        fmt(target.target_margin, 4),
        target.order_sz,
        target.max_position,
      ]),
    ),
  );
}

function renderActions(actions) {
  if (!actions.length) {
    html("portfolioActions", '<div class="empty">暂无调仓动作</div>');
    return;
  }
  html(
    "portfolioActions",
    table(
      [
        { label: "动作", type: "text" },
        { label: "合约", type: "text" },
        { label: "当前%", type: "num" },
        { label: "目标%", type: "num" },
        { label: "差值%", type: "num" },
        { label: "说明", type: "text" },
      ],
      actions.map((action) => [
        actionText(action.action),
        action.inst_id,
        fmt(action.current_weight_pct, 2),
        fmt(action.target_weight_pct, 2),
        fmt(action.delta_weight_pct, 2),
        action.note,
      ]),
    ),
  );
}

function renderExecution(intents) {
  if (!intents.length) {
    html("portfolioExecution", '<div class="empty">暂无执行草案</div>');
    return;
  }
  html(
    "portfolioExecution",
    table(
      [
        { label: "动作", type: "text" },
        { label: "合约", type: "text" },
        { label: "状态", type: "text" },
        { label: "前缀", type: "text" },
        { label: "配置", type: "text" },
      ],
      intents.map((intent) => [
        actionText(intent.action),
        intent.inst_id,
        badge(intent.status, intent.status === "runtime_config_ready" ? "ok" : "warn"),
        intent.bot_prefix || "--",
        basename(intent.runtime_config_path),
      ]),
      { rawColumns: [2] },
    ),
  );
}

function renderExposure(exposures) {
  if (!exposures.length) {
    html("portfolioExposure", '<div class="empty">暂无账户暴露</div>');
    return;
  }
  html(
    "portfolioExposure",
    table(
      [
        { label: "合约", type: "text" },
        { label: "多", type: "num" },
        { label: "空", type: "num" },
        { label: "净名义", type: "num" },
        { label: "估算保证金", type: "num" },
        { label: "未实现", type: "num" },
      ],
      exposures.map((item) => [
        item.inst_id,
        item.long_sz,
        item.short_sz,
        fmt(item.net_notional, 4),
        fmt(item.margin_estimate, 4),
        signed(Number(item.unrealized_pnl || 0), 4),
      ]),
    ),
  );
}

function activeEthBot() {
  const portfolioEth = portfolioBot("ETH-USDT-SWAP");
  return portfolioEth || { instId: "ETH-USDT-SWAP", source: "portfolio", running: false, runtimeConfig: portfolioRuntime("ETH-USDT-SWAP") || ETH_DEFAULTS };
}

function portfolioBot(instId) {
  const live = latestPortfolio?.live || latestPortfolio?.latestReport?.live || {};
  const bot = (live.bots || []).find((item) => item.instId === instId);
  if (!bot) return null;
  return { ...bot, source: "portfolio", botPrefix: bot.botPrefix || portfolioPrefix(instId) };
}

function portfolioRuntime(instId) {
  return (latestPortfolio?.latestReport?.runtimeConfigs || []).find((item) => item.instId === instId);
}

function portfolioPrefix(instId) {
  const base = String(instId || "").split("-")[0].toLowerCase();
  return base ? `p${base}`.slice(0, 8) : "";
}

function renderFills(fills) {
  if (!fills.length) {
    html("fills", '<div class="empty">暂无最近成交</div>');
    return;
  }
  html(
    "fills",
    table(
      [
        { label: "时间", type: "text" },
        { label: "合约", type: "text" },
        { label: "方向", type: "text" },
        { label: "仓位", type: "text" },
        { label: "张数", type: "num" },
        { label: "价格", type: "num" },
        { label: "PnL", type: "num" },
      ],
      fills.slice(0, 10).map((fill) => [
        time(Number(fill.fillTime || 0)),
        fill.instId,
        fill.side,
        fill.posSide,
        fill.fillSz,
        fill.fillPx,
        signed(Number(fill.fillPnl || 0) + Number(fill.fee || 0), 6),
      ]),
    ),
  );
}

function metric(label, value) {
  return `<div><dt>${esc(label)}</dt><dd>${esc(value ?? "--")}</dd></div>`;
}

function logicMetric(label, value) {
  return `<div class="logicMetric"><span>${esc(label)}</span><b>${esc(value ?? "--")}</b></div>`;
}

function rebalanceSummary(actions) {
  if (!actions.length) return "--";
  const entering = actions.filter((item) => item.action === "enter").length;
  const increasing = actions.filter((item) => item.action === "increase").length;
  const reducing = actions.filter((item) => ["decrease", "exit"].includes(item.action)).length;
  return `按目标权重与当前权重差值生成：进场 ${entering}，加仓 ${increasing}，减仓/退出 ${reducing}`;
}

function roleWeightPct(targets, role) {
  return targets.filter((target) => target.role === role).reduce((sum, target) => sum + Number(target.weight_pct || 0), 0);
}

function rebalanceTimingText(actions, allocation) {
  if (!actions.length) return "无动作";
  const threshold = allocation?.rebalance_threshold_pct ?? allocation?.rebalanceThresholdPct ?? "2";
  const actionable = actions.filter((item) => ["enter", "increase", "decrease", "exit"].includes(item.action)).length;
  const hold = actions.filter((item) => item.action === "hold").length;
  return `偏离 >= ${fmt(threshold, 2)}% · ${actionable} 个执行 / ${hold} 个持有`;
}

function adaptiveProfileText(rows) {
  if (!rows.length) return "--";
  const grids = rows.map((row) => Number(row.gridBps)).filter(Number.isFinite);
  if (!grids.length) return "高频滚动";
  return `高频滚动 · ${fmt(Math.min(...grids), 2)}-${fmt(Math.max(...grids), 2)} bps`;
}

function reasonText(note, allocation = {}) {
  const threshold = allocation?.rebalance_threshold_pct ?? allocation?.rebalanceThresholdPct ?? "2";
  return {
    "new target allocation": `原因：目标组合新增该合约，偏离达到 ${fmt(threshold, 2)}% 阈值，需要建立目标仓位。`,
    "below target allocation": `原因：当前权重低于目标权重，偏离达到 ${fmt(threshold, 2)}% 阈值，需要补足仓位。`,
    "above target allocation": `原因：当前权重高于目标权重，偏离达到 ${fmt(threshold, 2)}% 阈值，需要降低暴露。`,
    "close missing target": "原因：该合约不在目标组合内，需要退出。",
    "not selected by target portfolio": "原因：该合约不在目标组合内，需要退出。",
    "within threshold": `原因：偏离未超过 ${fmt(threshold, 2)}% 调仓阈值，暂不调仓。`,
  }[note] || `原因：${note || "--"}`;
}

function backtestStateText(state) {
  return {
    running: "运行中",
    completed: "完成",
    failed: "失败",
    unknown: "日志未完成",
    idle: "空闲",
  }[state] || state || "--";
}

function statusText(status) {
  return {
    runtime_config_ready: "运行配置已生成，仍为只读草案",
    skipped: "已跳过",
    blocked: "被阻止",
    pending: "等待中",
  }[status] || status || "--";
}

function modeText(mode) {
  return {
    live: "直接实盘",
    paper: "回测沙盘",
    backtest: "仅回测",
  }[mode] || mode || "--";
}

function signedMoney(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "--";
  return `${num >= 0 ? "+" : ""}${num.toFixed(6)} USDT`;
}

function trendLabel(value) {
  return value === "auto" ? "趋势自动" : value === "off" ? "趋势关闭" : value || "--";
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

function trendCheckText(summary) {
  const checked = summary?.trendCheckedCount ?? 0;
  const auto = summary?.trendAutoSelectedCount ?? 0;
  const off = summary?.trendOffSelectedCount ?? 0;
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
  if (/^state=inside/i.test(textValue)) {
    const mark = textValue.match(/mark=([^\s]+)/i)?.[1];
    return `区间内巡航：标记价 ${mark || "--"}。`;
  }
  if (/state=soft_low|state=soft_high|state=buffer/i.test(textValue)) {
    return "价格接近护栏：限制新增开仓，优先维护已有订单。";
  }
  if (/state=hard_low|state=hard_high/i.test(textValue)) {
    return "价格触发硬风控区域：暂停新增交易并等待处理。";
  }
  return textValue;
}

function table(headers, rows, options = {}) {
  const rawColumns = new Set(options.rawColumns || []);
  const headerHtml = headers
    .map((item) => `<th class="${item.type === "text" ? "text" : "num"}">${esc(item.label)}</th>`)
    .join("");
  const bodyHtml = rows
    .map(
      (row) =>
        `<tr>${row
          .map((value, index) => {
            const type = headers[index]?.type === "text" ? "text" : "num";
            const content = rawColumns.has(index) ? String(value ?? "--") : esc(value);
            return `<td class="${type}">${content}</td>`;
          })
          .join("")}</tr>`,
    )
    .join("");
  return `<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
}

function openSides(openGuard, trend) {
  const sides = openGuard?.allowedOpenSides || openGuard?.sides || trend?.allowedOpenSides || [];
  return sides.length ? sides.join(", ") : "close only";
}

function edgeSummary(edge, strategy) {
  const net = firstValue(edge?.netEstBps, strategy?.netMakerBps);
  const min = firstValue(edge?.minNetBps, strategy?.minNetBps);
  return `${fmt(net, 2)} / ${fmt(min, 2)} bps`;
}

function actionMix(actionsByType) {
  const entries = Object.entries(actionsByType || {}).filter(([, value]) => Number(value) !== 0);
  if (!entries.length) return "--";
  return entries.map(([key, value]) => `${actionText(key)} ${value}`).join(" / ");
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

function roleText(role) {
  return {
    core: "核心",
    satellite: "卫星",
  }[role] || role || "--";
}

function badge(value, level = "") {
  return `<span class="badge ${level}">${esc(value || "--")}</span>`;
}

function basename(path) {
  return String(path || "").split("/").filter(Boolean).at(-1) || "--";
}

function money(value) {
  if (value === undefined || value === null || value === "") return "--";
  return Number(value).toFixed(4);
}

function signed(value, digits = 6) {
  if (value === undefined || value === null || value === "" || Number.isNaN(Number(value))) return "--";
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}`;
}

function fmt(value, digits = 2) {
  if (value === undefined || value === null || value === "" || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function pctValue(value, digits = 2) {
  return value === undefined || value === null || value === "" ? "--" : `${fmt(value, digits)}%`;
}

function time(value) {
  if (!value) return "--";
  const date = typeof value === "number" ? new Date(value) : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function priceDigits(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 2;
  if (number >= 1000) return 2;
  if (number >= 1) return 4;
  return 6;
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function positionSize(snapshotData, posSide) {
  const position = (snapshotData?.positions || []).find((item) => item.posSide === posSide);
  return position?.pos;
}

function clamp(value, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return min;
  return Math.max(min, Math.min(max, number));
}

function text(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "--";
}

function html(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = value;
  const renderedContent = /<table|satelliteGrid|logicList/.test(String(value));
  el.classList.toggle("empty", !renderedContent);
}

function setStyle(target, key, value) {
  const el = target.startsWith(".") ? document.querySelector(target) : document.getElementById(target);
  if (el) el.style.setProperty(key, value);
}

function setConn(label, level) {
  setPill("connState", label, level);
}

function setPill(id, label, level) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = label;
  el.className = `pill ${level || "watch"}`;
}

function setDot(id, level) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `statusDot ${level || "watch"}`;
}

function colorSigned(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("positive", Number(value) > 0);
  el.classList.toggle("negative", Number(value) < 0);
}

function esc(value) {
  return String(value ?? "--")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

refresh();
setInterval(refresh, 8000);
