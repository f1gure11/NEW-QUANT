# TRADFI 美股合约盘中多周期动量研究

> 只读研究。信号来自公开美股现货数据，执行按 OKX TRADFI 合约 K 线模拟；不读取账户、不发送订单、不修改服务或实盘配置。

## 固定设计

- 因子：15/30/60/120 分钟、波动率归一化的多周期时间序列动量；至少两票同向，阈值 0.1 sigma。
- 时间：仅纽约常规交易日 09:30–16:00；每天重新暖机，最后一根常规时段 K 线收盘强平，绝不持隔夜。
- 数据：Yahoo Finance 公开 5m 美股 OHLCV 只用于信号；同时间戳 OKX TRADFI 永续 5m OHLCV 只用于执行。缺失、非交易日、早收市和不完整交易日全部排除。
- 执行：下一根合约 K 线开盘成交，默认每边 5 bps 手续费 + 5 bps 不利滑点；压力为双倍。没有根据训练、验证或测试结果调整周期、阈值或标的参数。

## 样本

- 所有合约共同完整交易日：43。
- 切分：训练 21 日，验证 11 日，测试 11 日。

| 标的 | OKX 合约 | 匹配交易日 | 现货 RTH K线 | 合约 RTH K线 | 精确时间戳匹配 |
| --- | --- | ---: | ---: | ---: | ---: |
| SOXL | SOXL-USDT-SWAP | 43 | 4680 | 3354 | 3354 |
| NVDA | NVDA-USDT-SWAP | 43 | 4680 | 3354 | 3354 |
| AMD | AMD-USDT-SWAP | 43 | 4680 | 3354 | 3354 |
| MU | MU-USDT-SWAP | 43 | 4680 | 3354 | 3354 |
| SNDK | SNDK-USDT-SWAP | 43 | 4680 | 3354 | 3354 |

## 当前合约流动性准入

> 这是报告生成时的 OKX 公共快照，只用于决定后续研究宇宙，不能代表历史每一根 K 线的真实盘口。

| 标的 | 合约 | 状态 | 价差 | 24h 估算换手 | 准入 | 原因 |
| --- | --- | --- | ---: | ---: | --- | --- |
| SOXL | SOXL-USDT-SWAP | live/3 | 0.710 bps | 218104366 USDT | True | - |
| NVDA | NVDA-USDT-SWAP | live/3 | 0.447 bps | 14880998 USDT | True | - |
| AMD | AMD-USDT-SWAP | live/3 | 0.208 bps | 13724659 USDT | True | - |
| MU | MU-USDT-SWAP | live/3 | 0.114 bps | 324738218 USDT | True | - |
| SNDK | SNDK-USDT-SWAP | live/3 | 0.082 bps | 1944345846 USDT | True | - |
| TSM | TSM-USDT-SWAP | live/3 | 0.238 bps | 1322939 USDT | False | turnover_below_limit |

## 样本外结果

| 标的 | 版本 | 收益 | PF | 最大回撤 | 交易 | 胜率 | 暴露 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SOXL | base | -2.8887% | 0.674 | 4.6285% | 65 | 26.15% | 67.60% |
| SOXL | cost_stress | -5.3824% | 0.498 | 6.3553% | 65 | 20.00% | 67.60% |
| NVDA | base | -3.5795% | 0.243 | 3.9151% | 71 | 16.90% | 67.72% |
| NVDA | cost_stress | -6.2819% | 0.105 | 6.5106% | 71 | 12.68% | 67.72% |
| AMD | base | -3.8306% | 0.387 | 4.2426% | 78 | 17.95% | 67.60% |
| AMD | cost_stress | -6.7870% | 0.225 | 6.9595% | 78 | 11.54% | 67.60% |
| MU | base | -5.9359% | 0.317 | 6.3448% | 78 | 20.51% | 67.83% |
| MU | cost_stress | -8.8272% | 0.203 | 9.0785% | 78 | 14.10% | 67.83% |
| SNDK | base | -2.7006% | 0.633 | 4.0881% | 72 | 23.61% | 67.25% |
| SNDK | cost_stress | -5.4621% | 0.421 | 6.0621% | 72 | 22.22% | 67.25% |

## 判定

- 状态：`research_only`。
- 最低研究样本：`True`；40 个共同交易日的历史覆盖要求：`True`。
- 全部合约通过基础测试：`False`；通过压力测试：`False`。
- No promotion path: the public 5-minute source is capped near 60 days, historical contract spreads are unavailable, and the experiment must be followed by a separately preregistered forward sample even if its historical rows pass.

## 数据边界

- 免费或公开不等于可直接实盘：Yahoo 是公开接口而非机构级逐笔/盘口源；其 5 分钟历史窗口很短。
- OHLC 无法恢复合约历史 bid/ask、盘口深度、资金费、强平或挂单排队。实际进场前仍须以 OKX 实时合约盘口筛选流动性，并做全新、不再调参的前瞻记录。
