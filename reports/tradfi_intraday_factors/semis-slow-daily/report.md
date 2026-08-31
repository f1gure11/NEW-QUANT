# TRADFI 美股合约盘中慢因子研究

> 只读研究。信号来自公开美股现货数据，执行按 OKX TRADFI 合约 K 线模拟；不读取账户、不发送订单、不修改服务或实盘配置。

## 固定设计

- 因子：前一交易日收盘已知的 20/60/120 日、波动率归一化多周期动量；至少两票同向，阈值 0.1 sigma。
- 时间：仅纽约常规交易日 09:30–16:00；最后一根常规时段 K 线收盘强平，绝不持隔夜。
- 数据：Yahoo Finance 公开日线美股 OHLCV 只用于信号；每日信号严格使用早于当日的最近一个已完成收盘。OKX TRADFI 5m OHLCV 只用于执行。缺失、非交易日、早收市和不完整交易日全部排除。
- 执行：下一根合约 K 线开盘成交，默认每边 5 bps 手续费 + 5 bps 不利滑点；压力为双倍。没有根据训练、验证或测试结果调整周期、阈值或标的参数。

## 样本

- 所有合约共同完整交易日：43。
- 切分：训练 21 日，验证 11 日，测试 11 日。

| 标的 | OKX 合约 | 交易日 | 日线因子K线 | 合约 RTH K线 | 做多日 | 做空日 | 空仓日 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SOXL | SOXL-USDT-SWAP | 43 | 2514 | 3354 | 43 | 0 | 0 |
| NVDA | NVDA-USDT-SWAP | 43 | 2514 | 3354 | 20 | 0 | 23 |
| AMD | AMD-USDT-SWAP | 43 | 2514 | 3354 | 43 | 0 | 0 |
| MU | MU-USDT-SWAP | 43 | 2514 | 3354 | 43 | 0 | 0 |
| SNDK | SNDK-USDT-SWAP | 43 | 372 | 3354 | 43 | 0 | 0 |

## 当前合约流动性准入

> 这是报告生成时的 OKX 公共快照，只用于决定后续研究宇宙，不能代表历史每一根 K 线的真实盘口。

| 标的 | 合约 | 状态 | 价差 | 24h 估算换手 | 准入 | 原因 |
| --- | --- | --- | ---: | ---: | --- | --- |
| SOXL | SOXL-USDT-SWAP | live/3 | 0.712 bps | 216821904 USDT | True | - |
| NVDA | NVDA-USDT-SWAP | live/3 | 0.447 bps | 14865666 USDT | True | - |
| AMD | AMD-USDT-SWAP | live/3 | 0.208 bps | 13705480 USDT | True | - |
| MU | MU-USDT-SWAP | live/3 | 0.114 bps | 323693817 USDT | True | - |
| SNDK | SNDK-USDT-SWAP | live/3 | 0.082 bps | 1940698862 USDT | True | - |
| TSM | TSM-USDT-SWAP | live/3 | 0.238 bps | 1312653 USDT | False | turnover_below_limit |

## 样本外结果

| 标的 | 版本 | 收益 | PF | 最大回撤 | 交易 | 胜率 | 暴露 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SOXL | base | -5.2562% | 0.499 | 9.1336% | 11 | 36.36% | 100.00% |
| SOXL | cost_stress | -5.6665% | 0.472 | 9.3425% | 11 | 36.36% | 100.00% |
| NVDA | base | -0.4718% | 0.778 | 2.2118% | 11 | 63.64% | 100.00% |
| NVDA | cost_stress | -0.9083% | 0.608 | 2.4054% | 11 | 54.55% | 100.00% |
| AMD | base | -2.5494% | 0.569 | 4.3238% | 11 | 36.36% | 100.00% |
| AMD | cost_stress | -2.9745% | 0.519 | 4.5677% | 11 | 36.36% | 100.00% |
| MU | base | -2.6465% | 0.627 | 4.9087% | 11 | 45.45% | 100.00% |
| MU | cost_stress | -3.0710% | 0.580 | 5.1316% | 11 | 45.45% | 100.00% |
| SNDK | base | -5.0643% | 0.565 | 7.4463% | 11 | 36.36% | 100.00% |
| SNDK | cost_stress | -5.4756% | 0.539 | 7.6253% | 11 | 36.36% | 100.00% |

## 判定

- 状态：`research_only`。
- 最低研究样本：`True`；40 个共同交易日的历史覆盖要求：`True`。
- 全部合约通过基础测试：`False`；通过压力测试：`False`。
- No promotion path: the available public contract-execution history is bounded, historical contract spreads are unavailable, and the experiment must be followed by a separately preregistered forward sample even if its historical rows pass.

## 数据边界

- 免费或公开不等于可直接实盘：Yahoo 是公开接口而非机构级逐笔/盘口源；日线能拉长因子历史，但合约执行样本仍然有限。
- OHLC 无法恢复合约历史 bid/ask、盘口深度、资金费、强平或挂单排队。实际进场前仍须以 OKX 实时合约盘口筛选流动性，并做全新、不再调参的前瞻记录。
