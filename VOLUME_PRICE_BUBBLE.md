# SKHY 量价气泡/反转指标（研究版）

当前主研究合约是 `SKHY-USDT-SWAP`。它和旧合约
`SKHYNIX-USDT-SWAP` 是两个独立的 OKX 合约，不能合并成交、参数或回测。

当前公开合约规格也不同：`SKHY-USDT-SWAP` 的最小/步长为 `0.01`、tick 为 `0.01`；旧 `SKHYNIX-USDT-SWAP` 的最小/步长为 `0.001`、tick 同为 `0.01`。因此本模块默认值固定指向 `SKHY-USDT-SWAP`，换旧合约时必须重新读取合约规格并单独回测。

## 研究依据

- Karpoff, *The Relation Between Price Changes and Trading Volume: A Survey*：
  [DOI 10.2307/2330874](https://doi.org/10.2307/2330874)。用于支持把价格变化和成交量联合分析，而不是只看价格指标。
- Blume, Easley & O'Hara, *Market Statistics and Technical Analysis: The Role of
  Volume*：[DOI 10.1111/j.1540-6261.1994.tb04424.x](https://doi.org/10.1111/j.1540-6261.1994.tb04424.x)。用于“成交量包含市场状态/信息”的方向性依据。
- Phillips, Shi & Yu, *Testing for Multiple Bubbles*：
  [DOI 10.1111/iere.12132](https://doi.org/10.1111/iere.12132)。GSADF 是价格序列的递归爆炸性检验，适合长样本泡沫识别；SKHY 上市时间太短，暂不把它硬套成分钟级进场信号。
- GitHub [mortenmus/Volume-Price-Phase-Shift-VPPS](https://github.com/mortenmus/Volume-Price-Phase-Shift-VPPS)：提出“价格动能领先成交量动能/成交量领先价格”的相位差思路，但仓库没有足够验证证据；本项目只参考概念，未复制代码。
- GitHub [Boulder-Investment-Technologies/lppls](https://github.com/Boulder-Investment-Technologies/lppls)：LPPLS 气泡拟合库，适合较长价格窗口和事后/预警研究；拟合成本和样本要求不适合作为当前 SKHY 的高频硬进场条件。

## 当前实现

`volume_price_bubble.py` 的每根完成 K 线计算：

1. 价格相对慢 EMA 的 ATR 偏离（价格是否过度延伸）。
2. 价格动能与 CLV×归一化成交量的方向性压力差（量价背离）。
3. 成交量异常 z 分数，以及“高成交量但价格结果很小”的吸收/出货分数。
4. 只有当气泡分数达到阈值、并且收盘突破最近短结构时，才生成下一根 K 线开盘的反转事件。

止损使用气泡极值外的 ATR 缓冲；止盈使用初始风险的 R 倍数；达到一定 R 后先推保本，再用 ATR 跟踪。OHLC 无法知道同一根 K 线先碰止盈还是止损时，回测按止损优先，避免美化结果。

## 使用

回测默认按 `SKHY-USDT-SWAP` 当前成交中观察到的成本近似：开仓 2 bps、出场 5 bps，并额外加入 2 bps 滑点压力；这不是交易所费率承诺，正式验证时仍要替换成账户实际费率。

只读研究/回测：

```bash
PYTHONPATH=. .venv/bin/python volume_price_bubble.py \
  --inst-id SKHY-USDT-SWAP --bar 1m --limit 300 --pages 24 --refresh \
  --train-bars 2400 --test-bars 600 --step-bars 600 \
  --output-dir reports/volume_price_bubble/skhy-1m-research
```

输出包括当前信号、成交明细、权益曲线和滚动样本外结果。该模块目前没有连接下单服务；通过样本外门禁前不能用于实盘开仓。
