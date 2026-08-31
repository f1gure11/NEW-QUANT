# 山寨币负资金费向零修复做空：冻结开发回放

- 模型：alt-negfund-reversion-short-v1
- 数据区间：2026-06-13T08:00:00Z 至 2026-08-07T19:00:00Z
- 证据等级：仅开发回放，不是预注册后的新样本
- 纸盘/实盘授权：否

## 规则

固定 6 个山寨永续；72 小时涨幅至少 20%，且为同一资金费时点候选中涨幅前 2；过去 24 小时近似成交额至少 1000 万 USDT；前次资金费不高于 -5 bps，最新仍低于 0，且至少向零修复 2 bps。资金费公布后的第一根 5 分钟开盘做空。每仓名义本金 5%，1 倍杠杆，最多两仓；8% 止损，24 小时时间退出；盈利状态下出现 1 小时跌幅不低于 4%、收盘位于小时振幅底部 25% 时，下一根 5 分钟开盘止盈。

## 整体结果

| 口径 | 收益 | PF | 最大回撤 | 交易数 | 资金费 | 手续费 | 滑点成本 | 最差7日 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 毛价格 | 0.000000% | 0.000 | 0.000000% | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 基础成本 | 0.000000% | 0.000 | 0.000000% | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 双倍成本 | 0.000000% | 0.000 | 0.000000% | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000% |

结论：当前共同历史没有触发冻结条件，收益、胜率和 PF 均不可评估；表中的 0 不是策略通过或保本。

## 时间顺序切分

| 区间 | 时间 | 毛价格 | 基础成本 | 双倍成本 | 基础PF | 交易数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| train | 2026-06-13T08:00:00Z - 2026-07-11T01:30:00Z | 0.000000% | 0.000000% | 0.000000% | 0.000 | 0 |
| validation | 2026-07-11T01:30:00Z - 2026-07-24T22:15:00Z | 0.000000% | 0.000000% | 0.000000% | 0.000 | 0 |
| test | 2026-07-24T22:15:00Z - 2026-08-07T19:00:00.000000001Z | 0.000000% | 0.000000% | 0.000000% | 0.000 | 0 |

## 样本与退出

- 原始信号：0
- 实际交易：0
- 未通过原因计数：{"earlier_funding_not_negative_enough": 1002, "funding_improvement_too_small": 993, "price_return_too_small": 984, "latest_funding_not_below_zero": 701}
- 退出原因：{}
- 合约分布：{}
- 平均决策到入场延迟：None 分钟

## 结论边界

- All replay data predates or overlaps the preregistration boundary and is development-only.
- The fixed current-contract universe creates survivorship bias and excludes delisted contracts.
- Historical quote turnover is approximated from candle volume, contract value, and close; historical bid/ask and depth are unavailable.
- Realized funding is observable only at its timestamp; entry is delayed to the first later 5-minute open.
- 无论本次结果好坏，都不能据此授权纸盘或实盘，也不能回看后修改冻结阈值。
