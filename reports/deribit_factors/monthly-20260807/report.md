# Deribit 期权信息因子与短周期回测

> 只读取 Deribit 公共历史行情；不读取账户、不下单、不修改实盘。

## 预注册依据

- Alexander & Imeraj (2020), *The Bitcoin VIX and Its Variance Risk Premium*, DOI `10.3905/jai.2020.1.112`：Deribit 期权可构造比特币隐含方差与方差风险溢价。
- Zulfiqar & Gulzar (2021), *Implied volatility estimation of bitcoin options and the stylized facts of option pricing*, DOI `10.1186/s40854-021-00280-y`：短期限 BTC 期权存在远期偏斜/微笑。
- Cremers & Weinbaum (2010), *Deviations from Put-Call Parity and Stock Return Predictability*, DOI `10.1017/S002210901000013X`：同执行价 Call-Put IV 差包含方向信息。
- Pan & Poteshman (2006), *The Information in Option Volume for Future Stock Prices*, DOI `10.1093/rfs/hhj024`：期权 Put-Call 成交量包含短期价格信息。
- Bollerslev, Tauchen & Zhou (2009), *Expected Stock Returns and Variance Risk Premia*, DOI `10.1093/rfs/hhp008`：方差风险溢价可与预期收益相关。

## 数据与边界

- 月度到期：2023-01-27 至 2026-06-26，共 42 个；按到期日 50%/25%/25% 划分训练、验证、测试。
- 有效 BTC/ETH 横截面观察共 84 个；期权长权利金结果覆盖 79 个。
- 每个因子只使用到入场时为止、最多陈旧 6 小时的期权成交；持有 Deribit 永续 24 小时。
- 永续主成本为双边共 12 bps，压力为 24 bps；每资产使用 10% 权益，无杠杆。
- 期权历史只有成交 OHLC、没有逐时 bid/ask；因此期权只作为信息源。长权利金对照使用此前 Tardis 的 72h ATM 经验半价差，BTC/ETH 每边 4.35%/3.64%。
- Pan–Poteshman 使用买方发起的新开仓量；Deribit 图表接口只有总成交量，无法区分方向和开平仓，因此这里的 Call/Put 总量比只是较弱代理。

## 因子 Rank IC

| 样本 | 因子 | 数量 | 对未来24h收益 IC | 对未来24h波动 IC |
| --- | --- | ---: | ---: | ---: |
| train | atm_call_put_iv_spread | 42 | -0.173 | +0.204 |
| train | risk_reversal_25d | 42 | -0.345 | +0.020 |
| train | call_put_volume_log_ratio | 42 | +0.164 | +0.037 |
| train | variance_risk_premium | 42 | -0.181 | +0.081 |
| train | butterfly_25d | 42 | -0.039 | +0.024 |
| validation | atm_call_put_iv_spread | 20 | -0.047 | +0.002 |
| validation | risk_reversal_25d | 20 | -0.032 | -0.451 |
| validation | call_put_volume_log_ratio | 20 | -0.018 | -0.420 |
| validation | variance_risk_premium | 20 | -0.101 | +0.295 |
| validation | butterfly_25d | 20 | +0.053 | +0.680 |
| test | atm_call_put_iv_spread | 22 | +0.059 | +0.112 |
| test | risk_reversal_25d | 22 | -0.019 | +0.130 |
| test | call_put_volume_log_ratio | 22 | -0.078 | +0.186 |
| test | variance_risk_premium | 22 | +0.176 | -0.019 |
| test | butterfly_25d | 22 | -0.342 | -0.326 |
| full | atm_call_put_iv_spread | 84 | +0.012 | +0.088 |
| full | risk_reversal_25d | 84 | -0.204 | -0.047 |
| full | call_put_volume_log_ratio | 84 | -0.020 | -0.004 |
| full | variance_risk_premium | 84 | -0.095 | +0.119 |
| full | butterfly_25d | 84 | -0.206 | +0.097 |

## 训练选择后的方向策略

训练选择：`risk_reversal_25d`；训练资格：`False`。账户收益按每资产 10% 权益计算。

| 样本/压力 | 交易 | 正收益 | 账户收益 | PF | 端点回撤 | 单笔中位净收益 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| train/normal | 42 | 13 | -1.7907% | 0.639 | 3.608% | -42.5 bps |
| validation/normal | 20 | 8 | -0.5222% | 0.772 | 0.816% | -26.0 bps |
| test/normal | 22 | 10 | -0.5609% | 0.725 | 1.527% | -56.2 bps |
| test/cost_stress | 22 | 10 | -0.8232% | 0.622 | 1.693% | -68.2 bps |
| test/latency_1h | 22 | 11 | -0.9157% | 0.594 | 1.820% | -3.9 bps |
| full/normal | 84 | 31 | -2.8514% | 0.691 | 3.608% | -39.1 bps |

### 防止测试段反选

测试段事后最好的 `atm_iv_spread` 为 +0.9052%，但它训练/验证/全样本分别为 -2.6281%/-0.0549%/-1.8007%。看到测试结果后不能改选它。

## 有界长权利金对照

训练选择：`long_iv_discount`；训练资格：`False`。每资产最多支付 0.5% 权益权利金。

| 样本/压力 | 交易 | 正收益 | 账户收益 | PF |
| --- | ---: | ---: | ---: | ---: |
| train/normal | 11 | 3 | -0.6318% | 0.267 |
| validation/normal | 12 | 1 | -1.3561% | 0.028 |
| test/normal | 10 | 2 | -0.6065% | 0.164 |
| test/cost_stress | 10 | 2 | -0.6579% | 0.138 |
| full/normal | 33 | 6 | -2.5739% | 0.130 |

## 决策

- 数量门禁：`False`。
- 状态：`research_only`；建议：`stop_short_term_strategy_research`。
- 即使通过，这些月份也已被本次检查，只能要求一个预注册的新鲜前向期；当前结果不授权仿真或实盘。
- 最大回撤只按月度事件端点计算，不能替代逐小时账户保证金压力。
