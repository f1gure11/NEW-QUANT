# GEX 关键价接针研究

`gex_pin_catcher_research.py` 是独立、只读的 BTC/ETH 研究器。它不读取
`.env`，不访问账户，不发单，也没有启动服务或实盘模式。

## 规则

- 仅在点时 `netGex > 0` 且快照未过期时做均值回归；负 Gamma 不接针。
- Put Wall 下方挂买单，Call Wall 上方挂卖单；墙位相同则围绕单一 pin
  strike 对称挂单。
- 墙位距离上一根收盘不超过 200 bps；每标的只保留一个仓位，每次使用
  20% 当前权益，无杠杆。
- 快照必须严格早于订单生效的 5 分钟 K 线，价格必须穿透限价 0.5 bps。
  同根双边触发跳过；新仓同根不能止盈，但可以按保守顺序止损。
- 正常成本为 maker 2 bps、风险退出 taker 5 bps 加 1 bps 滑点；压力情景
  为 maker 5 bps、taker 8 bps、2 bps 滑点及 2 bps 成交穿透。
- GEX 过期、转负或相关墙位移动超过 50 bps 时，在下一根可执行开盘风险
  退出。

参数网格仅在前 50% 数据上选择：墙外偏移 `0/10/25/50 bps`，退出组合
`25/50 bps/12 bars`、`40/80 bps/24 bars`、`60/120 bps/48 bars`，以及
GEX 最长年龄 `1/3/6h`。随后 25% 验证，最后 25% 测试，验证或测试结果不
用于换参。

## 当前结果

固定报告位于
`reports/gex_pin_catcher/btc-eth-20260807/report.md`。训练锁定参数为墙位
零偏移、25/50 bps 止盈止损、12 根最长持有和 6 小时 GEX 年龄。

训练、验证、测试中位收益分别为 `-0.182987%`、`-0.028704%` 和
`-0.154215%`；测试成本压力为 `-0.194187%`。36 个候选中只有 8 个达到
每标的至少 5 笔训练成交门槛，这 8 个的测试中位收益没有一个为正。测试
本身也只有 BTC 2 笔、ETH 4 笔，不能支持统计判断。

结论是 `research_only`：机制可以表达和重放，但当前没有成本后样本外
alpha，也没有足够测试成交。不得把 5 分钟 K 线穿价当作真实 maker 排队
成交；任何后续 paper 候选都必须使用全新、逐事件 WebSocket 订单簿与成交流
前向验证。

## 重放

```bash
PYTHONPATH=. .venv/bin/python gex_pin_catcher_research.py \
  --output-dir reports/gex_pin_catcher/btc-eth-20260807
```
