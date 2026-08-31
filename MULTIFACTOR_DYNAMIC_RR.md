# BTC/ETH 多因子动态胜率—盈亏比研究

这是一个只读研究实验，不读取账户、不启动服务、不发送订单。默认使用本地
`data/microstructure/` 中的 BTC-USDT-SWAP 和 ETH-USDT-SWAP 公共 REST 快照。

运行：

```bash
PYTHONPATH=. .venv/bin/python multifactor_dynamic_rr_research.py \
  --output-dir btc-eth-YYYYMMDD
```

模型用前 50% 的公共历史拟合 `StandardScaler + Ridge`，因子包括：

- 多周期动量；
- 深度、成交量、价差构成的流动性；
- 资产与 BTC 的 30/120 快照滚动相关性；
- RSI、EMA 趋势、Bollinger 偏离、区间位置和收益自相关；
- Alpha6、7、9、12、21、23、41、53、54、101 的数值实现。

REST 快照没有原生 OHLCV；Alpha101 使用连续 5 个中间价快照构造微型 bar，volume 使用
公开成交名义额。因此这里测试的是 Alpha101 公式在约 65 秒微结构数据上的改写，不是标准日频因子。

选择段只选择信号阈值、目标/止损波动率倍数、最低胜率、最低期望和持有上限。
入场时使用此前已平仓交易的 Beta 后验胜率，并把训练方向标签压缩为每个方向/置信桶最多
20 个等效先验样本；每次平仓后才更新后验。目标和止损按 30 快照波动率乘持仓窗口平方根，
再按信号置信度和胜率后验动态调整。盈亏平衡胜率包含双边手续费、滑点和当前价差。

## 2026-08-07 结果

选中参数为：阈值 `0.15`、目标波动率倍数 `1.0`、止损波动率倍数 `0.9`、最低胜率 `50%`、
最低期望 `2 bps`、最长持有 `60` 个快照。

| 区间 | 中位收益 | 中位期望 | 中位胜率 | 中位盈亏比 | 中位 PF | 最差回撤 | 交易 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 训练 | -0.0559% | -6.740 bps | 20.00% | 0.357 | 0.238 | 0.159% | 6 |
| 选择 | -0.3834% | -8.135 bps | 42.48% | 0.848 | 0.612 | 0.767% | 47 |
| 验证 | -0.3773% | -21.188 bps | 16.67% | 0.442 | 0.221 | 0.385% | 24 |
| 复用测试 | -0.5002% | -7.772 bps | 35.62% | 1.125 | 0.563 | 1.100% | 51 |

复用测试分标的：BTC 16 笔，胜率 31.25%，实际盈亏比 1.763，期望 -2.217 bps；ETH 35
笔，胜率 40.00%，实际盈亏比 0.486，期望 -13.328 bps。成本压力中位期望为
`-17.136 bps`，一快照延迟为 `-8.140 bps`。

结论：`quantitativePassOnReusedHistory=false`，仍为研究候选，不能据此进入纸面或实盘。
完整结果在 `reports/multifactor_dynamic_rr/btc-eth-20260807-final/`，包括
`summary.json`、`rows.csv`、`trades.csv` 和 `report.md`。数据是约 65 秒轮询的 REST 快照，
不是无损 WebSocket 逐笔流；任何后续尝试都需要新鲜前向数据和纸面仿真。

## 新鲜 WebSocket 前向样本

从 2026-08-07 04:35 UTC 起，`microstructure_ws_collect.py` 独立记录 OKX 公共
`books5`、`trades` 和 `tickers` 原始事件。长期采集由
`okx-microstructure-ws-collector.service` 运行；它不读取账户、不使用私有频道、也不发送订单。

在运行新模型前先执行成熟度审计：

```bash
PYTHONPATH=. .venv/bin/python microstructure_ws_audit.py \
  --input-root data/microstructure_ws \
  --output reports/multifactor_dynamic_rr/ws-data-audit.json
```

默认要求 BTC/ETH 三个频道分别覆盖至少 72 小时、最近事件不超过 180 秒、任一采集中断不超过
1 小时且无显著坏数据。
审计状态为 `collecting` 时禁止报告策略收益；只有
`ready_for_forward_backtest` 才能冻结模型设定并划分新的前向验证区间。72 小时只是最小管道门槛，
不是策略显著性或实盘准入门槛。
