# 100 USDT QQQ 纯合约离散优化

`qqq_small_account_contract_research.py` 把冻结的 QQQ 月频主动增强权重转换为 OKX
真实 `lotSz/minSz/ctVal`，专门回答 100 USDT 小账户能否在总 gross 1.2 或 1.5 倍
下构造一个仍受约束的纯永续合约组合。

脚本只读取 OKX 公共合约规格、现有公共 5 分钟 K 线和 realized funding 缓存。
它不加载 `.env`、不访问账户、不下单，也不修改服务或实盘配置。

固定离散规则：

- 沿用冻结的点时月频方向，不根据合约收益改变信号；连续持有并按月调仓。
- 主动 gross 不超过 20%。单股维持 1.5% 上限；只有一份交易所最小合约本身
  更大时，允许这一份不可避免的最小订单。
- 美元残差不超过 2%，beta 残差不超过 1%，每个行业残差不超过 2%，事前
  跟踪误差不超过 3%。
- 在硬约束内，最小化离散权重相对冻结权重的事前协方差偏离。43 天合约收益
  不进入优化目标。
- 基础成本每边 5 bps 手续费加 5 bps 滑点；压力成本翻倍；资金费按公开历史
  realized rate 计入。
- 月内若开盘时 gross 超过上限，只减少 QQQ 核心并计入换手成本；不会因为
  gross 低于上限而在月内主动补杠杆。

报告同时保留两种主动执行：`enhanced` 在最小合约条件下继续约束gross和中性；
`allMin` 则保留每个月所有非零旧方向，每只固定一份交易所最小合约，不再强制
主动gross、单股、beta、行业或TE约束。

运行：

```bash
PYTHONPATH=. .venv/bin/python qqq_small_account_contract_research.py \
  --output-dir reports/qqq_small_account_contract/small-100-20260808-v1
```

输出包括当前离散持仓、合约规格快照、月频调仓记录、1.2/1.5 倍增强组合与同
gross QQQ 合约对照的逐日收益和报告。所有结论仍是 `research_only`，不得把短
合约窗口解释为新的独立样本或实盘授权。
