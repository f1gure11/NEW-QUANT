# 订单流机器学习动态胜率与盈亏比研究

## 结论

机器学习可以动态估计某个订单流动作的胜率、条件平均盈利和条件平均亏损，
但本轮 BTC/ETH 实验没有得到成本后的可交易优势。梯度提升模型在验证集选择的
最低预测净期望为 0 bps，但验证和复用测试的实际收益、实际期望与利润因子仍全部
为负。当前状态只能是 `research_only`，不能进入仿真或实盘，更不能增加杠杆。

主报告位于：
`reports/orderflow_ml_probability/btc-eth-20260806/report.md`。

## 论文路线

1. [The Price Impact of Order Book Events](https://doi.org/10.1093/jjfinec/nbt003)
   说明短期价格变化与订单流不平衡（OFI）之间的关系。本实验使用标准化的最优价
   OFI、盘口深度不平衡及主动成交不平衡作为基础特征。
2. [Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book](https://doi.org/10.1142/S2382626616500064)
   支持将买卖队列不平衡作为极短周期方向预测变量。当前 REST 快照无法恢复队列
   优先级，因此只测试不平衡信号，不能测试真实 maker 成交。
3. [DeepLOB](https://doi.org/10.1109/TSP.2019.2907260)
   使用卷积与循环结构从密集 L2 事件张量预测价格方向。它要求逐事件、等长的订单簿
   序列；当前约 65 秒一次的 REST 快照不满足其数据假设，因此未强行套用。
4. [Deep Order Flow Imbalance](https://doi.org/10.1111/mafi.12413)
   将多档、多尺度 OFI 与深度模型结合。它是未来 WebSocket 事件数据的合理路线，
   不是当前稀疏快照的合理基线。
5. [Predicting Good Probabilities with Supervised Learning](https://doi.org/10.1145/1102351.1102430)
   说明分类排序能力不等于可靠概率，支持使用独立校准集和 Isotonic 校准。本实验的
   决策目标因此是校准后的净期望，而不是分类准确率。

## 开源方案评估

许可证信息在 2026-08-06 通过 GitHub API 核验。

| 项目 | 许可证 | 本轮处理 | 判断 |
| --- | --- | --- | --- |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn) | BSD-3-Clause | 已使用本地 1.7.2 | 实际完成梯度提升、逻辑回归和 Isotonic 校准测试 |
| [Freqtrade / FreqAI](https://github.com/freqtrade/freqtrade) | GPL-3.0 | 只评估，未引入 | 适合交易与模型管线，但不能补回缺失的逐事件 L2 数据 |
| [hftbacktest](https://github.com/nkaz001/hftbacktest) | MIT | 只评估，未引入 | 适合未来事件回放、延迟和队列成交模型 |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0 | 只评估，未引入 | 可作为未来事件驱动研究和仿真管线 |
| [DeepLOB 公开复现](https://github.com/zcakhaa/DeepLOB-Deep-Convolutional-Neural-Networks-for-Limit-Order-Books) | 未声明 | 未复制代码 | 当前数据与 PyTorch 环境均不匹配，且许可证不清晰 |
| [mlfinlab](https://github.com/hudson-and-thames/mlfinlab) | GitHub API: NOASSERTION | 只借鉴概念 | 三重障碍实现为本项目独立代码，没有复制仓库代码 |

框架本身不会产生优势。本轮只引入已经安装且许可证清晰的 scikit-learn，避免为了
试框架扩大依赖面或把 K 线模型错误用于 L2 事件问题。

## 实验设计

- 标的：`BTC-USDT-SWAP`、`ETH-USDT-SWAP`。
- 区间：2026-07-02 15:28 UTC 至 2026-08-06 16:53 UTC。
- 时间切分：前 40% 训练模型，随后 10% 只校准概率，再 25% 选择模型与净期望
  门槛，最后 25% 作探索性复用测试。
- 特征：盘口不平衡、主动成交不平衡、OFI、价差、多尺度均值、短期收益、波动率、
  交互项、时段及标的标记，共 23 项；所有特征只使用决策时点及此前数据。
- 动作：多空两个方向乘以四组预先固定的 TP/SL/最长持有期，共八个动作。
- 标签：按未来可成交 bid/ask、双边费用、滑点、数据断档和三重障碍计算净收益。
- 胜率：`HistGradientBoostingClassifier` 后接独立校准段的 Isotonic 校准。
- 盈亏比：分别回归 `E[win|x]` 与 `E[loss|x]`，动态盈亏比为
  `E[win|x] / E[loss|x]`。
- 决策：动态净期望为
  `p * E[win|x] - (1-p) * E[loss|x]`，只选择预测净期望最高且超过验证门槛的动作；
  模型可以空仓。
- 执行：每边 5 bps taker 费和 1 bps 不利滑点，按可成交报价进出，每笔 20% 权益，
  无杠杆，单标的同一时间只允许一个仓位。

## 实验结果

验证段选择 `hist_gradient_dynamic`，最低预测净期望门槛为 0 bps。

| 区间 | 中位收益 | 实际胜率 | 实际盈亏比 | 实际期望 | PF | 预测胜率 | 预测期望 | 校准差 | 交易数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 验证 | -0.7739% | 26.00% | 0.816 | -10.484 bps | 0.276 | 65.44% | +6.825 bps | 39.44 pct | 74 |
| 复用测试 | -0.2636% | 34.40% | 1.106 | -8.801 bps | 0.559 | 60.80% | +6.584 bps | 26.41 pct | 33 |

复用测试逐标的均亏损：BTC 14 笔、收益 -0.3955%、PF 0.380；ETH 19 笔、
收益 -0.1317%、PF 0.738。成本压力、延迟一张快照、强制持续交易、逻辑回归和原
固定规则基线也全部为负。

模型的核心失败不是“分类准确率不够高”，而是预测与实现不一致：测试中模型预测
胜率的跨标的中位数为 60.80%，实际只有 34.40%，高估 26.41 个百分点；预测净期望
为正，实际净期望却为负。此时加 10 倍杠杆只会放大负期望、费用和爆仓风险。

## 解释边界

这次最终 25% 与此前规则型订单流实验使用过同一段历史，所以只能称为“探索性复用
测试”，不能再称为独立最终测试。REST 采样还会遗漏轮询之间的逐笔事件，无法评估
队列位置、撤单顺序、maker 成交率与真实延迟。

下一轮有效实验应先保存无损 WebSocket 逐事件订单簿和成交数据，并预先登记特征、
标签、门槛及准入规则，然后在尚未查看的未来数据上验证。至少应同时满足：验证、
测试、成本压力与延迟压力均盈利；每个标的 PF 不低于 1.10；概率校准误差不超过
5 个百分点；每个标的不少于 30 笔；最差回撤不超过 3%。满足前仍不应仿真或实盘。

## 复现

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python orderflow_ml_probability_research.py \
  --output-dir btc-eth-20260806

PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_orderflow_ml_probability_research -v
```

实验不会读取 `.env`、访问账户、启动服务或发送订单。
