# 主观板块进攻计划

`aggressive_sector_plan.py` 是一个只读的人工复核计划工具，用于把“我判断某个美股板块上涨/下跌”转换成固定篮子、ATR 止损止盈、盘中确认和风险仓位。它不读取账户，不读取 `.env`，不下单，不启动 bot，也不生成 live 命令。

半导体观点另有一次性实盘部署 `active_sector_live.py`。它没有改变本研究模板的
`research_only` 状态，而是用独立、当日到期的人工授权调用相同冻结规则。视图可管理 SNDK/SOXL
篮子或独立的 SKHY 单腿，
使用独立订单前缀、状态、健康文件和 halt，不拥有 QQQ 的 12 腿。

## 固定篮子

| 板块 | 组合 | 风险分配 | 止损距离 |
|---|---|---:|---:|
| `semiconductor` | SNDK 60% / SOXL 40% | 2% 权益风险预算 | `0.5 x ATR14`，限制 4.5%-6.5% |
| `sk_hynix` | SKHY 100% | 2% 权益风险预算 | `0.5 x ATR14`，限制 4.5%-6.5% |
| `cloud_ai` | PLTR 60% / CRWD 40% | 2% 权益风险预算 | `0.55 x ATR14`，限制 3%-5% |
| `crypto_fintech` | COIN 60% / HOOD 40% | 2% 权益风险预算 | `0.55 x ATR14`，限制 3.5%-6% |
| `data_center_power` | VRT 60% / GEV 40% | 2% 权益风险预算 | `0.55 x ATR14`，限制 4%-6% |
| `mega_cap_platform` | META 60% / AMZN 40% | 2% 权益风险预算 | `0.55 x ATR14`，限制 2.5%-4.5% |
| `ev_growth` | TSLA 100% | 2% 权益风险预算 | `0.55 x ATR14`，限制 3.5%-5.5% |
| `precious_metals` | XAU 100% | 2% 权益风险预算 | `0.5 x ATR14`，限制 0.8%-2.0% |

ATR 使用数据湖中已完成交易时段的 5 分钟 K 线聚合出的日线 ATR14。美股篮子用纽约 09:30-16:00；`precious_metals` 用 COMEX 18:00-17:00（跨自然日，周日晚开、周五下午收）。未走完收盘前最后一根 5 分钟 K 的时段不会进入 ATR。固定规则不根据当天涨幅临时换股。止盈为 1R 平 50%、1.5R 处理剩余仓位，这三个值均来自配置；如果合约最小单位无法拆分两档，计划会阻断。实际价格会按合约 `tickSz` 修正，仓位会按 `ctVal`、`lotSz`、`minSz` 修正。实盘还会把名义再压进主动策略 0.40 gross 上限。

有实际入场价时，工具另外读取 OKX 公共接口中当日已确认的 5 分钟 K 线。只有美股常规时段开盘至少 15 分钟、距离收盘至少 60 分钟，声明方向同时通过 session VWAP 与 15 分钟开盘区间突破确认，并且填入价格与最新公共收盘价偏离不超过 100 bps，每条腿才会进入 `ready_for_review`。任一腿数据不足、方向不确认、价格误填、合约元数据异常、最小下单单位超预算或总保证金超限，整个篮子都会 `blocked`。

## 使用

没有实际入场价时只输出 ATR 参考：

```bash
PYTHONPATH=. .venv/bin/python aggressive_sector_plan.py \
  --sector semiconductor --direction long --equity 42 --leverage 3
```

开盘至少 15 分钟后填入当时的实际入场价，每条腿各填一次。程序会独立计算 VWAP 与开盘区间门禁，不以人工文字确认替代：

```bash
PYTHONPATH=. .venv/bin/python aggressive_sector_plan.py \
  --sector semiconductor --direction long --equity 42 --leverage 3 \
  --entry-price SNDK-USDT-SWAP=1271.83 \
  --entry-price SOXL-USDT-SWAP=133.32
```

默认输出到独立目录 `reports/aggressive_sector_plan/<UTC时间>/sector_plan.json` 和 `.md`，不会覆盖上一份计划。JSON 包含配置内容哈希 `playbookId`，便于确认计划使用了哪一版固定规则。`ready_for_review` 只代表计算完成，仍需人工检查账户可用余额、已有仓位、挂单和滑点；它不是交易授权。

## 风控边界

- 杠杆只改变保证金占用，不提高 2% 的价格风险预算；另列 0.5% 成本/滑点缓冲。
- 单次计划最多两条腿、不在同一份计划里跨板块。实盘可以同时登记多个已授权观点，各管各的合约和清仓时刻。
- 不补仓、不摊平、止损后不重进、不拿到下一个交易时段。
- 默认使用 3x，允许范围 2x-5x；聚合保证金超过权益 50% 时阻断。
- 盘中门禁只读公共行情；ATR 只读数据湖。任何公共数据缺失都按失败关闭处理。
- 这是主观 beta 执行模板，不是已验证 alpha，持续标记为 `research_only`。任何实盘都需要当前会话的明确授权和独立账户预检。

## 一次性实盘边界

- 实盘仍是当天口头授权，不是研究升级。授权写在 `config/active_sector_live.json`，过期后不能复用。
- 2026-08-19：今日主动视图切换为 `SKHY-USDT-SWAP` 单腿多头，2x，纽约 15:50 清仓，20:05 UTC 到期。
- 2026-08-12：半导体多头，SNDK/SOXL，纽约 15:50 清仓。
- 2026-08-13：贵金属空头，XAU 单腿，COMEX 时段，纽约 16:50 清仓，21:05 UTC 授权到期。
- 入场必须通过该篮子自己的 session VWAP 与 15 分钟开盘区间；空头要求价格在 VWAP 和下沿之下。
- 价格风险预算 2% 权益，另列 0.5% 成本缓冲；3x 隔离保证金，主动 gross 上限 0.40。黄金止损更窄，通常会被 0.40 上限压小名义。
- 与 QQQ 共用账户时合计 gross 上限 1.60；超限先退出主动腿，不改变 QQQ 的月频信号。
- 成交后按实际均价维护两档 OCO：1R 平一半，1.5R 平剩余；两档都带完整对应数量的止损。
- 止损后不重进；到期或清仓时刻无条件平掉主动腿。
