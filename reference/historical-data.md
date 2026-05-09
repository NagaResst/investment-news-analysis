# 历史数据引用规范

## 🎯 核心概念

**历史数据引用**是指从本地归档文件中读取相关基金过去的趋势信息，用于：
1. 了解基金的历史表现和趋势
2. 验证当前预测的准确性
3. 构建基金的长期画像
4. 避免重复搜索已归档的信息

---

## 📂 本地文件结构

### 主要文件位置

```
投资新闻归档/
├── index.json                    # 索引文件（入口）
├── 2026-04/                      # 按月归档
│   └── 2026-04-26/              # 按日归档
│       ├── summary_2026-04-26.md    # 每日汇总
│       ├── item_summaries/          # 单条信息
│       └── raw_data/                # 原始数据
└── 2026-05/
    └── 2026-05-03/
        └── summary_2026-05-03.md
```

---

## 📖 读取流程

### 步骤一：读取 index.json

**文件位置**：`投资新闻归档/index.json`

**文件内容示例**：
```json
{
  "version": "2.0",
  "last_updated": "2026-05-03T18:30:00",
  "summaries": [
    {
      "date": "2026-05-03",
      "file_path": "2026-05/2026-05-03/summary_2026-05-03.md",
      "funds_mentioned": ["003984", "005827", "006567"],
      "key_events": ["央行降准", "宁德时代财报"],
      "tags": ["新能源", "货币政策", "季报", "降准"],
      "sentiment_index": {
        "003984": 74,
        "005827": 62,
        "overall": 68
      },
      "has_prediction": true,
      "has_position_advice": true
    },
    {
      "date": "2026-04-26",
      "file_path": "2026-04/2026-04-26/summary_2026-04-26.md",
      "funds_mentioned": ["003984", "005827"],
      "key_events": ["新能源政策", "白酒消费税"],
      "tags": ["新能源", "消费税", "产业政策", "白酒"],
      "sentiment_index": {
        "003984": 81,
        "005827": 55,
        "overall": 68
      },
      "has_prediction": false,
      "has_position_advice": true
    }
  ]
}
```

**新增字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tags` | string[] | 该日归档涉及的关键主题标签，用于跨日期主题搜索 |
| `sentiment_index` | object | 各基金当日舆情指数（0-100），以及整体均值 |
| `has_prediction` | bool | 该日 summary 是否包含走势预测报告 |
| `has_position_advice` | bool | 该日 summary 是否包含仓位决策建议 |

**读取方法**：
```python
import json

with open('投资新闻归档/index.json', 'r', encoding='utf-8') as f:
    index = json.load(f)
    
# 获取所有 summary 列表
summaries = index['summaries']
```

---

### 步骤二：筛选目标基金的历史记录

**目标**：找到包含指定基金的所有历史 summary

**筛选逻辑**：
```python
target_fund = "003984"  # 目标基金代码

# 筛选包含目标基金的 summary
fund_summaries = [
    s for s in summaries 
    if target_fund in s['funds_mentioned']
]

# 按时间倒序排列（最近的在前）
fund_summaries.sort(key=lambda x: x['date'], reverse=True)

# 取最近10条
recent_summaries = fund_summaries[:10]
```

**输出示例**：
```
找到基金 003984 的 10 条历史记录：
- 2026-05-03: summary_2026-05-03.md
- 2026-04-26: summary_2026-04-26.md
- 2026-04-19: summary_2026-04-19.md
- ...
```

---

### 步骤三：读取 Summary 文件内容

**读取单个 Summary**：
```python
def read_summary(file_path):
    full_path = f"投资新闻归档/{file_path}"
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()

# 读取最近的 summary
latest_summary = read_summary(recent_summaries[0]['file_path'])
```

**Summary 文件结构**：
```markdown
# 投资新闻日报 - 2026-05-03

## 📊 一、核心指标速览

| 基金代码 | 最新净值 | 日涨跌幅 | 资金流向 | 舆情指数 |
|---------|---------|---------|---------|---------|
| 003984  | 3.45元  | +1.2%   | +2.3亿  | 75/100  |
| 005827  | 2.89元  | -0.5%   | -0.8亿  | 62/100  |

## 🔥 二、今日重要事件

### 003984 长城久富核心成长混合
- **事件**：基金经理张坤发表观点，看好新能源板块
- **影响**：✅ 利好
- **来源**：[财联社](https://...)

## 📈 三、重仓股动态

### 宁德时代（占比8.5%）
- Q1净利润207亿，同比+48.5%
- 机构评级：买入（中信证券）

## 💬 四、机构观点汇总

| 机构 | 评级 | 目标价 | 变化 |
|-----|------|-------|------|
| 中信证券 | 买入 | 3.80元 | 维持 |
| 中金公司 | 增持 | 3.65元 | 上调 |
```

---

### 步骤四：提取趋势指标

从多个 summary 中提取关键指标，构建趋势图

#### 1. 净值走势

**提取方法**：
```python
import re

def extract_nav(summary_content, fund_code):
    """从 summary 中提取基金净值"""
    pattern = rf"{fund_code}\s*\|\s*([\d.]+)元\s*\|\s*([+-][\d.]+%)"
    matches = re.findall(pattern, summary_content)
    if matches:
        return {
            'nav': float(matches[0][0]),
            'change': matches[0][1]
        }
    return None

# 提取多条记录的净值
nav_history = []
for summary in recent_summaries:
    content = read_summary(summary['file_path'])
    nav_data = extract_nav(content, "003984")
    if nav_data:
        nav_history.append({
            'date': summary['date'],
            'nav': nav_data['nav'],
            'change': nav_data['change']
        })
```

**趋势分析**：
```
净值走势（近10天）：
2026-04-20: 3.32元 (+0.8%)
2026-04-23: 3.35元 (+0.9%)
2026-04-26: 3.38元 (+1.2%)
2026-04-29: 3.40元 (+0.6%)
2026-05-03: 3.45元 (+1.2%)

趋势：持续上涨，累计涨幅 +3.9%
```

#### 2. 资金流向

**提取方法**：
```python
def extract_cash_flow(summary_content, fund_code):
    """提取资金流向"""
    pattern = rf"{fund_code}.*?([+-]\d+\.\d+)亿"
    match = re.search(pattern, summary_content)
    if match:
        return float(match.group(1))
    return 0

# 计算累计资金流向
total_flow = sum(extract_cash_flow(read_summary(s['file_path']), "003984") 
                 for s in recent_summaries)
```

**趋势判断**：
```
资金流向（近10天）：
累计净流入：+12.5亿
日均流入：+1.25亿
趋势：持续净流入，市场看好
```

#### 3. 舆情指数

**提取方法**：
```python
def extract_sentiment(summary_content, fund_code):
    """提取舆情指数"""
    pattern = rf"{fund_code}.*?(\d+)/100"
    match = re.search(pattern, summary_content)
    if match:
        return int(match.group(1))
    return 50  # 默认中性

# 计算平均舆情
sentiments = [extract_sentiment(read_summary(s['file_path']), "003984") 
              for s in recent_summaries]
avg_sentiment = sum(sentiments) / len(sentiments)
```

**舆情分级**：
```
舆情指数分级：
- 80-100: 极度乐观
- 60-79: 偏正面
- 40-59: 中性
- 20-39: 偏负面
- 0-19: 极度悲观

当前：75/100 → 偏正面
```

#### 4. 机构评级变化

**提取方法**：
```python
def extract_ratings(summary_content, fund_code):
    """提取机构评级"""
    ratings = []
    # 查找机构评级表格
    pattern = r'\|.*?\|.*?(买入|增持|中性|减持|卖出)\|.*?\|(维持|上调|下调)\|'
    matches = re.findall(pattern, summary_content)
    for rating, change in matches:
        ratings.append({'rating': rating, 'change': change})
    return ratings

# 统计评级变化
all_ratings = []
for summary in recent_summaries:
    content = read_summary(summary['file_path'])
    all_ratings.extend(extract_ratings(content, "003984"))

# 统计
upgrades = sum(1 for r in all_ratings if r['change'] == '上调')
downgrades = sum(1 for r in all_ratings if r['change'] == '下调')
maintained = sum(1 for r in all_ratings if r['change'] == '维持')
```

**评级趋势**：
```
机构评级变化（近30天）：
- 上调：2次
- 维持：5次
- 下调：0次

结论：机构态度偏正面，无下调记录
```

---

### 步骤五：构建历史画像

将提取的指标整合成基金的历史画像

**画像模板**：
```markdown
## 📊 基金历史趋势画像 - {基金代码}

### 基础信息
- **基金名称**：{基金全称}
- **基金经理**：{经理姓名}
- **成立日期**：{成立日期}
- **最新规模**：{规模}亿元

### 近期表现（近1个月）

#### 净值走势
- **起始净值**：3.32元（2026-04-20）
- **最新净值**：3.45元（2026-05-03）
- **累计涨幅**：+3.9%
- **最大单日涨幅**：+1.2%
- **最大回撤**：-0.3%
- **趋势判断**：📈 稳步上涨

#### 资金流向
- **累计净流入**：+12.5亿元
- **日均流入**：+1.25亿元
- **最大单日流入**：+3.2亿元（2026-04-26）
- **趋势判断**：💰 持续吸金

#### 舆情指数
- **平均舆情**：75/100
- **最高舆情**：82/100（2026-04-26，发布利好消息）
- **最低舆情**：68/100（2026-04-22，市场调整）
- **趋势判断**：😊 偏正面

#### 机构评级
- **上调次数**：2次
- **维持次数**：5次
- **下调次数**：0次
- **主流评级**：买入/增持
- **趋势判断**：⭐ 机构看好

### 重仓股稳定性
- **前十大持仓变化率**：15%（季度调仓）
- **最大变动个股**：新增比亚迪（占比4.2%）
- **剔除个股**：减仓格力电器（从5.1%降至2.3%）
- **稳定性评价**：中等，适度调仓

### 关键事件回顾
1. **2026-04-26**：基金经理发表看好新能源观点 → 当日净值+1.2%
2. **2026-04-23**：重仓股宁德时代发布财报 → 带动基金上涨
3. **2026-04-20**：央行降准 → 成长股受益

### 综合评估
- **短期趋势**：📈 上涨趋势明确
- **中期趋势**：➡️ 震荡上行
- **风险等级**：⚠️ 中等（行业集中度较高）
- **投资建议**：持有为主，逢低加仓
```

---

## 🔄 历史数据的应用场景

### 场景一：预测前的趋势参考

**用途**：在进行新预测前，了解基金的历史表现

**操作**：
1. 读取近30天的历史数据
2. 识别趋势模式（上涨/下跌/震荡）
3. 结合当前信息，判断趋势是否延续

**示例**：
```
历史趋势：近30天持续上涨，累计+8.3%
当前信息：重仓股发布利好财报
预测：短期继续上涨概率大（70%）
```

### 场景二：预测准确性验证

**用途**：验证之前的预测是否准确

**操作**：
1. 找到预测日期的 summary
2. 对比预测值与实际值
3. 计算准确率和偏差

**详细说明**：参见 [预测验证机制](prediction-verification.md)

### 场景三：避免重复搜索

**用途**：检查某条信息是否已经归档

**操作**：
```python
def is_already_archived(news_title, archive_dir):
    """检查新闻是否已归档"""
    item_summaries_dir = f"{archive_dir}/item_summaries"
    for file in os.listdir(item_summaries_dir):
        with open(f"{item_summaries_dir}/{file}", 'r') as f:
            content = f.read()
            if news_title in content:
                return True
    return False

# 搜索前先检查
if not is_already_archived("宁德时代Q1财报", "投资新闻归档/2026-04/2026-04-26"):
    # 执行搜索
    search_news("宁德时代 Q1 财报")
else:
    print("该新闻已归档，跳过搜索")
```

---

## ⚠️ 注意事项

1. **时间范围选择**：
   - 短期预测：读取近7-14天数据
   - 中期预测：读取近30天数据
   - 长期预测：读取近90天数据

2. **数据完整性检查**：
   - 检查 summary 文件是否存在
   - 检查关键字段是否缺失
   - 如数据不足，补充搜索

3. **异常值处理**：
   - 识别并标记异常数据（如单日涨跌超过5%）
   - 分析异常原因（重大事件/市场波动）
   - 决定是否纳入趋势分析

4. **数据更新频率**：
   - 每个交易日结束后更新
   - 重大事件发生时立即更新
   - 保持 index.json 同步更新

5. **版本控制**：
   - 使用 Git 管理历史数据
   - 每次更新后提交
   - 便于回溯和对比

---

## 📊 数据提取工具函数

提供常用的数据提取函数库

```python
"""
历史数据提取工具
位置：skills/investment-news-analysis/scripts/data_extractor.py
"""

import json
import re
import os
from datetime import datetime, timedelta

class HistoryDataExtractor:
    def __init__(self, archive_root="投资新闻归档"):
        self.archive_root = archive_root
        
    def load_index(self):
        """加载 index.json"""
        index_path = os.path.join(self.archive_root, "index.json")
        with open(index_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_fund_history(self, fund_code, days=30):
        """获取基金最近N天的历史记录"""
        index = self.load_index()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        fund_summaries = []
        for summary in index['summaries']:
            summary_date = datetime.strptime(summary['date'], '%Y-%m-%d')
            if summary_date >= cutoff_date and fund_code in summary['funds_mentioned']:
                fund_summaries.append(summary)
        
        return sorted(fund_summaries, key=lambda x: x['date'], reverse=True)
    
    def extract_nav_trend(self, fund_code, days=30):
        """提取净值趋势"""
        histories = self.get_fund_history(fund_code, days)
        nav_data = []
        
        for history in histories:
            content = self.read_summary(history['file_path'])
            nav = self.parse_nav(content, fund_code)
            if nav:
                nav_data.append({
                    'date': history['date'],
                    'nav': nav['nav'],
                    'change': nav['change']
                })
        
        return nav_data
    
    def read_summary(self, file_path):
        """读取 summary 文件"""
        full_path = os.path.join(self.archive_root, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def parse_nav(self, content, fund_code):
        """解析净值数据"""
        pattern = rf"{fund_code}\s*\|\s*([\d.]+)元\s*\|\s*([+-][\d.]+%)"
        match = re.search(pattern, content)
        if match:
            return {
                'nav': float(match.group(1)),
                'change': match.group(2)
            }
        return None

# 使用示例
extractor = HistoryDataExtractor()
nav_trend = extractor.extract_nav_trend("003984", days=30)
print(f"近30天净值数据：{len(nav_trend)}条记录")
```

---

## 🔍 按标签跨日期查询

利用 `index.json` 中新增的 `tags` 字段，可以快速回答"过去3个月有哪些关于储能政策的新闻"类问题：

```python
def search_by_tag(tag, index, days=90):
    """
    按标签搜索历史归档
    
    Args:
        tag: 搜索标签（如"储能政策"、"碳酸锂"、"降准"）
        index: 已加载的 index.json 内容
        days: 搜索最近N天
    
    Returns:
        list of matching summary metadata
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    results = []
    
    for summary in index['summaries']:
        summary_date = datetime.strptime(summary['date'], '%Y-%m-%d')
        if summary_date < cutoff_date:
            continue
        # 模糊匹配标签
        if any(tag in t for t in summary.get('tags', [])):
            results.append(summary)
    
    return sorted(results, key=lambda x: x['date'], reverse=True)

# 使用示例
results = search_by_tag("储能", index, days=90)
print(f"近3个月含'储能'标签的归档：{len(results)} 条")
for r in results:
    print(f"  {r['date']} - {r['key_events']}")
```

**标签规范**：归档时标签应使用简短关键词，常用标签示例：
- 行业类：`新能源`、`白酒`、`半导体`、`医疗`
- 事件类：`季报`、`财报`、`分红`、`调仓`
- 政策类：`降准`、`产业政策`、`消费税`
- 宏观类：`GDP`、`CPI`、`货币政策`

---

**版本**：v2.0  
**最后更新**：2026-05-07  
**维护者**：NagaResst
