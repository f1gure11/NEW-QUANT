# TRADFI 美股合约盘中因子研究

`tradfi_intraday_factor_research.py` 是一个隔离的只读实验：公开美股现货
5 分钟或日线数据只生成信号，OKX TRADFI 永续合约的公开 5 分钟 K 线只模拟执行。
它不读取 `.env`、账户或私有端点，不会下单、启动服务或改动任何实盘配置。

## 固定假设

- 标的仅限有明确美股现货映射且已有合约 K 线的 `SOXL`、`NVDA`、`AMD`、`MU`、`SNDK`、`TSM`。
- 因子固定为当前多周期动量的盘中版本：5 分钟 K 线的 `3/6/12/24` 根回看、至少两票、`0.1 sigma` 阈值。它不做任何按标的或测试结果的参数搜索。
- 只在 NYSE 常规时段（纽约时间 09:30--16:00）交易；不完整交易日、周末、主要美国假期及早收市日不使用；每日收盘平仓，无隔夜头寸。
- 交易以合约下一根 K 线开盘、每边 5 bps 手续费和 5 bps 不利滑点处理；测试期另外进行双倍成本压力。

## 慢因子模式

使用 `--factor-mode slow_daily` 时，信号改为 Yahoo 公开日线的固定
`20/60/120` 日多周期动量和 20 日波动率归一化。每个 RTH 交易日只读取
严格早于当日的最近一个完成日线收盘，至少两周期同向才改变方向；方向只在
当天 RTH 合约内执行，收盘强平，不持隔夜。慢因子模式没有按标的、区间或结果
再选参数。

```bash
PYTHONPATH=. .venv/bin/python tradfi_intraday_factor_research.py \
  --factor-mode slow_daily --contract-pages 60 \
  --output-dir reports/tradfi_intraday_factors/semis-slow-daily
```

这会把长历史用于因子暖机，但真实执行样本仍由 OKX 合约 K 线的共同区间决定。
若测试不通过，不应继续扫描其它慢周期来挖掘结果；应重新预注册一个新假设并从
之后的实时数据建立前瞻样本。

本次固定实验得到 43 个共同完整交易日，按 21/11/11 日切分。11 日严格样本外中，
基础成本下 SOXL、NVDA、AMD、MU、SNDK 分别为 `-5.2562%`、`-0.4718%`、
`-2.5494%`、`-2.6465%`、`-5.0643%`，双倍成本下仍全部为负。当前窗口的慢信号
几乎全为做多，说明长期趋势方向并没有转化为可用的日内合约收益。报告位于
`reports/tradfi_intraday_factors/semis-slow-daily/report.md`，判定保持
`research_only`，不进入仿真或实盘。

## 数据选择

Yahoo Finance 的 chart endpoint 提供免费公开的短期 5 分钟 OHLCV，适合
建立可复现的研究样本，但它不是“开源”逐笔数据，也通常只保留约 60 个自然日。
它不能回答合约历史盘口深度、bid/ask、排队、资金费或实际强平价。

因此，Yahoo 只适合作为因子输入；执行收益必须仍使用 TRADFI 合约 K 线，任何
前瞻试验还必须以 OKX 实时盘口的成交量、价差和深度另行过滤。免费日线数据可做
慢因子训练，但不能替代盘中执行研究；要覆盖多年 1--5 分钟数据和逐笔成交，通常
需要持牌数据源或自行从现在开始采集。

## 运行

现有仓库的 30 页合约缓存可直接运行：

```bash
PYTHONPATH=. .venv/bin/python tradfi_intraday_factor_research.py \
  --output-dir reports/tradfi_intraday_factors/semis-rth-initial
```

第一次运行会把公共 Yahoo 原始 K 线缓存在 `data/tradfi_intraday/`。要明确刷新该
公开缓存才添加 `--refresh-underlyings`。研究报告会保持 `research_only`，即使某个
历史区间为正，也不授权仿真或实盘。

若需要与 Yahoo 的短期窗口取得更长的共同区间，可使用已有的公开 OKX 拉取器刷新
60 页合约 K 线；这仍只读取无鉴权市场端点：

```bash
PYTHONPATH=. .venv/bin/python tradfi_intraday_factor_research.py \
  --contract-pages 60 --refresh-contracts \
  --output-dir reports/tradfi_intraday_factors/semis-rth-60page
```
