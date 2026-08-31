# OKX GEX 估算

本项目的 GEX 页面只读计算，不调用下单接口。BTC/ETH/SOL 使用 OKX 原生期权；OKX 的股票/ETF 永续没有对应的 OKX 期权链，因此使用 OKX 股票合约交易额筛选标的，再读取公开美股期权链。

## 数据与公式

对每个期权合约使用：

```text
GEX($ / 标的 1% 变动)
  = gammaBS × (OI 合约数 × ctMult) × spot² × 0.01
```

页面默认优先统计 45 天内到期的合约；若近端样本不足，会回退到全部未到期合约并降低建议等级。当前 OKX 公开期权链可覆盖 BTC、ETH、SOL。现货和永续合约交易额使用稳定币计价市场的 24h 成交量估算，用来排序和做市场背景，不等同于期权 GEX。

Call 使用正号、Put 使用负号。这是常见的 dealer positioning 假设，不是 OKX 公布的做市商真实仓位；GEX 只能辅助主观交易，不能单独作为开仓理由。

## 美股合约数据源与 15 分钟硬门槛

股票/ETF 部分优先使用 Nasdaq 的公开 `option-chain` JSON 接口。它返回
`AS OF` 时间、期权买卖价和 Open Interest；项目用 Black–Scholes 中间价反解
IV，再计算 BS gamma。CBOE delayed-quotes JSON 是回退源，参考了开源
[gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) 的数据路径。

美股数据的源时间戳必须不超过 900 秒；超过后后端返回 `stale`，前端只显示
“不展示旧 GEX 数值”，不会用缓存数字冒充新数据。接口缓存 TTL 仍为 300 秒，
并且返回缓存前会再次检查每个美股源时间戳。OKX `instCategory=3` 的股票/ETF
永续按交易额取前 8 个，并强制保留 `SPCX/SNDK/SKHY/SKHYNIX`（若 OKX 当前有该合约）。
实测 `SPCX`、`SNDK`、`SKHY` 有可用链；`SKHYNIX` 没有同名公开美股期权链，因此明确标记不可用。

这里的美股 GEX 是外部股票期权链对 OKX 合约标的的代理估算，不代表 OKX 永续
本身存在期权，也不代表真实做市商仓位。Nasdaq/CBOE 数据可能有延迟、期权 OI
也可能不是盘中实时变化；它适合观察和研究，不作为自动交易输入。

## 参考实现

- [crypto-gamma-dashboard](https://github.com/sfdcShrikant/crypto-gamma-dashboard)：Binance 版完整 GEX 看板，算法和页面结构参考价值最高。
- [Crypto.Gex](https://github.com/lohith-mahesh/Crypto.Gex)：Deribit 版终端，包含 gamma wall、gamma flip 和波动结构。
- [crypto_gamma_exposure](https://github.com/schepal/crypto_gamma_exposure)：BTC 期权研究 Notebook。
- [OKX API 文档](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-option-market-data)：期权 Greeks、OI、合约乘数和标的指数的来源。
- [Nasdaq option-chain API](https://api.nasdaq.com/api/quote/AAPL/option-chain?assetclass=stocks)：美股公开期权链、OI、买卖价和 `AS OF` 时间来源。
- [gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker)：开源 CBOE GEX 计算参考，验证了公开 delayed-quotes 数据路径。
- [Option Gamma and Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4256259)：研究 gamma 与价格收益关系的参考资料；论文不是实时交易系统。

## 接口

- `GET /api/gex`：返回 5 分钟缓存的 GEX 和交易额排行。
- `GET /api/gex?refresh=1`：强制重新读取公开数据。
- `GET /api/portfolio/latest?includeAccount=1`：控制台和只读观测台使用的组合数据中包含 `gex` 字段。

后端实现位于 `gex_estimator.py`、`equity_gex.py`，前端渲染位于 `web/gex.js`。当前实现仅展示和生成主观交易提示，不会自动下单。

## 30 分钟–6 小时纸面策略

原有的动量、EMA/MACD、RSI/布林、ATR/Donchian 策略没有引用 GEX。新增的
`gex_strategy.py` 是独立的纸面/回测程序，不读取账户、不设置杠杆、不下单，也没有
systemd 实盘入口：

- 正 Gamma：价格靠近 Put/Call 墙并出现反转 K 线时，尝试向区间中部均值回归。
- 负 Gamma：只有穿越墙位、EMA 趋势和成交量同时确认时，才顺势跟随突破。
- 使用 5 分钟 K 线，最短 6 根（30 分钟），最长 72 根（6 小时）；默认单边费率和滑点合计按 7 bps 计入。

运行一次纸面信号：

```bash
PYTHONPATH=. .venv/bin/python gex_strategy.py --once
```

需要持续观察时可以显式运行 `--loop --interval 300`，但目前没有安装或启动这个循环服务。
dashboard 的 GEX 缓存 TTL 是 300 秒：页面每 10 秒读取组合状态时，后端只在缓存过期后的下一次请求重新计算；点击“刷新 GEX”会强制立即重算。因此它是“最多每 5 分钟自动更新”，不是后台定时器每 5 分钟无条件请求一次。

点时回测：

```bash
PYTHONPATH=. .venv/bin/python gex_strategy.py --backtest \
  --inst-id BTC-USDT-SWAP \
  --candle-file BTC-USDT-SWAP=data/backtest/BTC-USDT-SWAP_5m_300x48.csv
```

回测只接受与价格时间重叠的历史 GEX 快照，禁止用当前快照回填旧行情。2026-07-16 首次采集后，现有本地 5 分钟价格数据最晚到 2026-07-10，当前状态是历史样本不足，尚无可信的收益率结论。
