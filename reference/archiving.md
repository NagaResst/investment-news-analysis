# 归档流程详解

## 🎯 核心原则

1. **即时归档**：每次搜索完成后立即保存，不要等待
2. **关联性评估**：评分≥50才保存
3. **双重备份**：单条 Summary (Markdown) + 原始数据 (JSON)
4. **每日汇总**：基于 item_summaries 生成 summary

---

## 📋 完整流程

### 步骤1：执行搜索

使用 search_web 工具搜索相关信息。

### 步骤2：关联性评估

对每条结果评分（0-100分）：

**评分维度**：
1. **是否直接提及基金代码** (+40分)
   - 标题或摘要中包含基金代码或名称
   
2. **是否涉及重仓股** (+30分)
   - 持仓占比 >5%：+30分
   - 持仓占比 3-5%：+25分
   - 持仓占比 1-3%：+15分
   
3. **信息来源权威性** (+20分)
   - 官方渠道（证监会、交易所、公司财报）：+20分
   - 权威媒体（财新、证券时报、东方财富）：+15分
   - 社区讨论（雪球、股吧）：+5分
   
4. **时效性** (+10分)
   - 最近1天：+10分
   - 最近1周：+7分
   - 最近1月：+5分

**判断标准**：
- **高 (80-100)**：必须保存
- **中 (50-79)**：建议保存  
- **低 (<50)**：不保存

### 步骤3：生成单条 Summary

为每条高/中关联信息生成独立 Markdown 文件：

**新增字段：舆情元数据（必填）**

```markdown
### [2026-04-26] 宁德时代Q1净利润207亿同比增48.5%

**核心要点**：宁德时代2026年Q1实现营收1291亿元(+52.45%)、净利润207亿元(+48.52%)，显著超市场预期，储能销量占比提升至25%。

**影响判断**：✅ 利好 - 业绩超预期验证龙头地位，储能业务成为第二增长曲线

**舆情评分**：+1（利好）
**来源类型**：official（官方财报）
**持仓权重**：0.85（宁德时代占嘉实新能源持仓8.5%，8.5×10=85，上限1.0→0.85）
**发布时间**：2026-04-26

**相关持仓**：嘉实新能源(持仓8.37%，第一大重仓)

**信息来源**：[东方财富网](https://wap.eastmoney.com/a/202604153706309798.html)

**抓取时间**：2026-04-26 15:01:00

---
```

**舆情评分规则**：
- `+1`：利好（业绩超预期、政策利好、评级上调、资金流入等）
- `0`：中性（例行公告、无明显影响的行业动态）
- `-1`：利空（业绩不及预期、政策打压、评级下调、重大负面事件）

**持仓权重速查**：
- 直接提及基金代码/名称 → `1.0`
- 重仓股 → `min(持仓占比 × 10, 1.0)`（如占比8.5% → 0.85）
- 行业政策 → `0.4`
- 宏观经济 → `0.2`

**保存位置**：
```
日常工作流/投资新闻归档/2026-04/2026-04-26/item_summaries/001_宁德时代Q1财报.md
```

### 步骤4：保存 JSON 原始数据

同时保存结构化 JSON 数据到 raw_data 目录。

**保存位置**：
```
日常工作流/投资新闻归档/2026-04/2026-04-26/raw_data/stocks/宁德时代.json
```

### 步骤5：重复步骤1-4

对所有搜索轮次执行相同流程：
- 第1轮：基金基本信息 → `fund_003984_basic.json`
- 第2轮：重仓股动态 → `stocks/*.json`
- 第3轮：行业政策 → `policy/*.json`
- 第4轮：宏观经济 → `macro/*.json`

### 步骤6：生成每日汇总 Summary

所有搜索完成后，读取 `item_summaries/` 目录下的所有文件，生成汇总 summary。

**输出文件**：
```
日常工作流/投资新闻归档/2026-04/2026-04-26/summary_2026-04-26.md
```

---

## 📁 目录结构示例

```
日常工作流/投资新闻归档/2026-04/2026-04-26/
├── item_summaries/
│   ├── 001_宁德时代Q1财报.md
│   ├── 002_工信部绿色设计指南.md
│   ├── 003_十五五储能规划.md
│   └── 004_碳酸锂价格暴涨.md
├── raw_data/
│   ├── fund_003984_basic.json
│   ├── stocks/
│   │   └── 宁德时代.json
│   ├── policy/
│   │   └── news_150200.json
│   └── macro/
│       └── data_150300.json
└── summary_2026-04-26.md
```

---

## ⚠️ 常见错误

### ❌ 错误1：最后统一保存

**错误做法**：
- 执行所有搜索
- 最后才统一保存

**正确做法**：
- 每轮搜索后立即保存
- 防止会话中断导致数据丢失

### ❌ 错误2：不评估关联性

**错误做法**：
- 保存所有搜索结果
- 包括低质量信息

**正确做法**：
- 只保存评分≥50的信息
- 过滤低关联内容

### ❌ 错误3：遗漏舆情元数据

**错误做法**：
- 生成单条 summary 时只写 `+1 / 0 / -1`，忽略来源类型和持仓权重

**正确做法**：
- 每条 summary 必须同时记录 `sentiment`、`source_type`、`holding_weight` 三个字段
- 这是加权舆情指数计算的必要输入

---

## 📊 加权舆情指数计算

### 单条 summary 必填字段（更新）

```markdown
**舆情评分**：+1（利好）
**来源类型**：head_media（官方/财报/券商研报/头部媒体/社区 之一）
**持仓权重**：0.85（直接=1.0；重仓股=持仓占比×10，上限1.0；行业=0.4；宏观=0.2）
**发布时间**：2026-04-26（用于计算时效衰减）
```

### 权重体系

#### 1. 来源权威性权重 `w_source`

| 来源类型 | 标识符 | 权重 |
|---------|--------|------|
| 官方渠道（证监会/交易所/公司财报） | `official` | 1.0 |
| 券商研报（中信/中金/华泰等） | `research` | 0.9 |
| 头部财经媒体（财联社/证券时报） | `head_media` | 0.8 |
| 一般财经媒体 | `media` | 0.5 |
| 社区讨论（雪球/股吧） | `community` | 0.3 |

#### 2. 持仓相关性权重 `w_holding`

| 关联类型 | 权重计算 | 示例 |
|---------|---------|------|
| 直接提及基金代码/名称 | 1.0 | "003984 净值上涨" |
| 重仓股新闻 | 持仓占比 × 10（上限1.0） | 宁德时代占8.5% → 0.85 |
| 行业政策 | 0.4 | "新能源补贴延续" |
| 宏观经济 | 0.2 | "央行降准" |

#### 3. 时效衰减权重 `w_time`

| 距今天数 | 权重 |
|---------|------|
| 当天 | 1.0 |
| 1-3 天 | 0.8 |
| 4-7 天 | 0.5 |
| 8-30 天 | 0.2 |
| > 30 天 | 0.05 |

### 加权舆情指数公式

$$S_{\text{raw}} = \frac{\sum_{i=1}^{n} s_i \times w_{\text{source},i} \times w_{\text{holding},i} \times w_{\text{time},i}}{\sum_{i=1}^{n} w_{\text{source},i} \times w_{\text{holding},i} \times w_{\text{time},i}}$$

映射到 0-100：$S_{\text{score}} = (S_{\text{raw}} + 1) \times 50$（因为 $s_i \in \{-1, 0, +1\}$，raw 值域为 $[-1, +1]$）

### 资金流向修正系数 `k_flow`

$$S_{\text{final}} = S_{\text{score}} \times k_{\text{flow}}$$

| 当日资金流向 | `k_flow` | 说明 |
|------------|---------|------|
| 强净流入（>5亿） | 1.2 | 情绪+行动共振，放大信号 |
| 轻微净流入（0-5亿） | 1.05 | 轻微加强 |
| 中性（±0.5亿内） | 1.0 | 不修正 |
| 轻微净流出（-3-0亿） | 0.85 | 情绪与行动背离，压缩 |
| 强净流出（<-3亿） | 0.7 | 强烈背离，大幅压缩 |

> **背离信号的意义**：舆情正面但资金流出 → 机构在高情绪中离场，需警惕；舆情负面但资金流入 → 机构低调建仓，可能是逆向机会。

### 完整计算实现

```python
import math
from datetime import datetime

# 权重配置
SOURCE_WEIGHTS = {
    "official": 1.0,
    "research": 0.9,
    "head_media": 0.8,
    "media": 0.5,
    "community": 0.3,
}

FLOW_CORRECTION = {
    # (下界, 上界): k_flow
    (5, float('inf')): 1.2,
    (0, 5): 1.05,
    (-0.5, 0): 1.0,
    (-3, -0.5): 0.85,
    (float('-inf'), -3): 0.7,
}

def time_weight(publish_date_str, today_str=None):
    today = datetime.strptime(today_str, "%Y-%m-%d") if today_str else datetime.now()
    pub = datetime.strptime(publish_date_str, "%Y-%m-%d")
    days = (today - pub).days
    if days <= 0:   return 1.0
    if days <= 3:   return 0.8
    if days <= 7:   return 0.5
    if days <= 30:  return 0.2
    return 0.05

def get_flow_correction(net_flow_billion):
    for (lo, hi), k in FLOW_CORRECTION.items():
        if lo <= net_flow_billion < hi:
            return k
    return 1.0

def calculate_weighted_sentiment(items, net_flow_billion=0):
    """
    items: list of dict，每条包含:
        sentiment      : +1 / 0 / -1
        source_type    : "official" / "research" / "head_media" / "media" / "community"
        holding_weight : float (0.0 - 1.0)
        publish_date   : "YYYY-MM-DD"
    net_flow_billion: 当日资金净流入（亿元，负=流出）
    """
    weighted_sum = 0.0
    weight_total = 0.0

    for item in items:
        w_s = SOURCE_WEIGHTS.get(item["source_type"], 0.5)
        w_h = min(item["holding_weight"], 1.0)
        w_t = time_weight(item["publish_date"])
        w   = w_s * w_h * w_t

        weighted_sum += item["sentiment"] * w
        weight_total += w

    if weight_total == 0:
        return 50, False

    s_raw   = weighted_sum / weight_total          # [-1, +1]
    s_score = (s_raw + 1) * 50                     # [0, 100]
    k_flow  = get_flow_correction(net_flow_billion)
    s_final = min(100, max(0, round(s_score * k_flow)))

    alert = s_final < 30 or (s_final - s_score * 1.0) < -15  # 资金流出导致大幅压缩也预警
    return s_final, alert


# 使用示例
items = [
    {"sentiment": +1, "source_type": "official",   "holding_weight": 0.85, "publish_date": "2026-04-26"},
    {"sentiment": +1, "source_type": "research",   "holding_weight": 0.85, "publish_date": "2026-04-25"},
    {"sentiment":  0, "source_type": "media",      "holding_weight": 0.4,  "publish_date": "2026-04-24"},
    {"sentiment": -1, "source_type": "community",  "holding_weight": 0.4,  "publish_date": "2026-04-20"},
]
score, alert = calculate_weighted_sentiment(items, net_flow_billion=2.3)
# 输出：score=74, alert=False
```

### 输出示例

```
加权舆情指数：74/100
  原始加权分：0.48（映射前）
  资金流向修正：+2.3亿 → k=1.05
  预警状态：否

明细：
  宁德时代财报（official, w=0.85, 今天）    → +1 × 0.85 = 贡献大
  机构评级上调（research, w=0.85, 昨天）    → +1 × 0.76 = 贡献大
  行业政策（media, w=0.4, 3天前）           → 0 × 0.20 = 无贡献
  社区讨论看空（community, w=0.4, 7天前）   → -1 × 0.06 = 贡献极小
```

---

**舆情指数解读**：

| 指数区间 | 含义 | 操作参考 |
|---------|------|---------|
| 80-100 | 高权重信源极度乐观 | ⚠️ 注意过热，考虑减仓 |
| 60-79 | 加权后偏正面 | ✅ 正常持仓 |
| 40-59 | 加权后中性 | ✅ 观望 |
| 20-39 | 加权后偏负面 | ⚠️ 审视持仓 |
| 0-19 | 高权重信源持续负面 | 🔍 逆向机会或基本面恶化，需深度分析 |

**突变预警触发条件**（满足任一）：
- 加权指数单日下降 ≥ 30 点
- 资金流向修正导致指数压缩 > 15 点（背离信号）
- 连续 3 天加权指数 < 40

---

## 🔄 日常操作流程

**每天收盘后**：
1. 执行 3-5 轮搜索
2. 每轮搜索后立即保存（自动生成单条 summary + JSON，含舆情评分）
3. 生成每日汇总 summary（含舆情指数计算）
4. 更新 index.json（含 tags 和 sentiment_index 字段）
5. 提交到 Git

---

**返回主文档**：[SKILL.md](../SKILL.md)
