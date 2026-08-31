# 因子过滤与周期选择

`factor_filter_cycle_research.py` 是隔离的只读研究。它不读取 `.env`、账户或私有接口，不发送订单，也不修改任何实盘配置。

实验使用已有 BTC/ETH 约 65 秒公共 REST 快照，在同一组 46 个价格、波动率、趋势效率、偏度、半方差、OI、Funding 和时间因子上比较：

- 因子维度过滤：全部 Ridge、稳定 IC 加相关性剪枝、mRMR、分块 ElasticNet 稳定选择；
- 信号时间过滤：不平滑、严格单边 EWMA、严格单边 Kalman；
- 周期：原始 1 倍、适度放宽 3 倍、慢周期 6 倍采样步长。

所有候选同时按美洲盘与非美洲盘分开回测。美洲盘固定为纽约本地工作日 09:30–16:00，使用 IANA 时区规则自动处理夏令时；非美洲盘为其余时间。两者沿用同一个全时段时序训练模型，但候选排名与成交模拟分开进行；分盘版本在会话边界归零信号，并在首个边界外可成交快照平仓，不把跨时段损益混入该时段。

研究依据包括 mRMR（`10.1109/TPAMI.2005.159`）、Stability Selection（`10.1111/j.1467-9868.2010.00740.x`）、FDR（`10.1111/j.2517-6161.1995.tb02031.x`）、Kalman filtering（`10.1115/1.3662552`）以及多重因子检验门槛（`10.1093/rfs/hhv059`）。开源接口和许可证核对了 scikit-learn（BSD-3-Clause）、tsfresh（MIT）、mrmr-selection（MIT）与 pykalman；本项目没有复制其源码或新增运行依赖。

运行：

```bash
PYTHONPATH=. .venv/bin/python factor_filter_cycle_research.py \
  --end-time 2026-08-07T16:32:13.913Z \
  --output-dir reports/factor_filter_cycles/btc-eth-20260807
```

前 40% 数据只用于过滤和拟合，随后 10% 选择候选，之后 25% 验证，最后 25% 为已复用测试。任何正结果仍需全新预注册前向数据确认。
正式候选还要求选择段每个标的至少 12 笔；交易数不足的慢周期高分结果只作为探索诊断，不取得选择资格。
