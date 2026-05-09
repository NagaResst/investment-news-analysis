# 预测验证机制

## 🎯 核心目标

**预测验证**是指在生成新的预测之前，先验证历史预测的准确性，然后基于验证结果调整预测模型参数。

**为什么需要验证**：
1. 评估预测模型的可靠性
2. 发现预测偏差并修正
3. 提高未来预测的准确性
4. 建立可追溯的预测记录

---

## ⚡ 短期预测与历史验证规范（必须遵守）

> 本节约束日报中**「短期预测」章节**和**「历史预测验证」章节**的写法，与下方的中长期验证流程相互独立。

### 规则一：每日日报必须包含「短期预测」章节

每份 summary 的**末尾**（数据来源之后）必须包含以下格式的「短期预测」章节，作为后续报告验证的来源：

```markdown
## 短期预测（1-4周）

> 以下为方向性预测，后续报告需在净值出现明显变化时逐条验证。

| 编号 | 基金 | 预测方向 | 预计区间 | 依据摘要 | 预测日期 |
|------|------|---------|---------|---------|---------|
| S1 | 嘉实新能源新材料A(003984) | ⬇️ 震荡偏弱 | 3.20–3.40 | 锂电板块资金持续流出，宁德时代无新催化 | YYYY-MM-DD |
| S2 | 易方达科创50联接C(011609) | ⬆️ 偏强 | 1.26–1.35 | 纳指创新高传导，存储芯片需求旺盛 | YYYY-MM-DD |
| S3 | 财通新视野灵活配置A(005851) | ➡️ 震荡 | 4.90–5.20 | 半导体+光通信双轮，方向切换中 | YYYY-MM-DD |
| S4 | 华商新趋势优选(166301) | ⬆️ 偏强 | 17.5–19.0 | 光通信+军工主线，与市场强势方向吻合 | YYYY-MM-DD |
```

**要求**：
- 每条预测必须有**明确方向**（⬆️ 偏强上涨 / ⬇️ 偏弱下跌 / ➡️ 震荡）
- 必须有**预计净值区间**（而非只写方向）
- 必须有**1-2句依据**
- 至少覆盖主要持仓基金（嘉实新能源新材料A(003984)、易方达科创50联接C(011609)、财通新视野灵活配置A(005851)、华商新趋势优选(166301)）
- 记录**预测日期**，供后续验证时追溯

### 规则二：「历史预测验证」章节必须来源于历史「短期预测」

生成当日日报时，**必须先读取近期 summary 的「短期预测」章节**，找到已到期或已有足够净值数据可验证的预测，再填写「历史预测验证」。

**操作步骤**：
1. 从 index.json 获取近 1-4 周的 summary file_path 列表
2. 逐一读取，定位 `## 短期预测` 章节，提取各条预测
3. 对比今日实际净值，判断预测是否已可验证
4. 填写验证结果

**如果近期报告均不存在「短期预测」章节**，必须如实说明，**绝对禁止**根据历史报告的观察项或关注要点反向推断"预测内容"：

```markdown
## 历史预测验证

> ⚠️ 近期报告（截至 YYYY-MM-DD）均无「短期预测」章节，本轮无可验证的预测。
> 本报告起开始建立短期预测记录，后续报告可正常验证。

**本轮准确率**：N/A（无历史预测可供验证）
```

### 规则三：验证结果填写规范

当存在历史「短期预测」可验证时：

```markdown
## 历史预测验证

| 编号 | 预测日期 | 基金 | 原预测方向 | 原预测区间 | 当前净值 | 是否准确 |
|------|---------|------|---------|---------|---------|--------|
| S1 | 2026-05-09 | 嘉实新能源新材料A(003984) | ⬇️ 震荡偏弱 | 3.20–3.40 | 3.28（验证日2026-05-16）| ✅ 准确 |
| S2 | 2026-05-09 | 易方达科创50联接C(011609) | ⬆️ 偏强 | 1.26–1.35 | 1.21（验证日2026-05-16）| ❌ 错误 |

**本轮准确率**：1/2 = 50%
**说明**：S2预测偏强但实际下跌，下轮对科创50预测区间下调，方向改为震荡。
```

**准确性判断标准**：
- ✅ 准确：当前净值落在预测区间内，且方向吻合
- ❌ 错误：净值超出预测区间，或方向相反
- ⚠️ 部分准确：净值超出区间但方向正确（偏差<10%）

---

## 📋 验证流程

### 步骤一：找到待验证的预测

**定位方法**：
1. 从 index.json 中找到包含预测的 summary
2. 筛选出有"预测报告"或"走势预测"章节的记录
3. 按时间排序，找出需要验证的预测

**示例**：
```python
import json

def find_predictions(fund_code, archive_root="投资新闻归档"):
    """找到指定基金的所有预测记录"""
    index_path = f"{archive_root}/index.json"
    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)
    
    predictions = []
    for summary in index['summaries']:
        if fund_code in summary['funds_mentioned']:
            file_path = f"{archive_root}/{summary['file_path']}"
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 查找预测章节
                if "## 📈 走势预测" in content or "## 预测报告" in content:
                    predictions.append({
                        'date': summary['date'],
                        'file_path': summary['file_path'],
                        'content': content
                    })
    
    return predictions

# 使用
predictions = find_predictions("003984")
print(f"找到 {len(predictions)} 条预测记录")
```

---

### 步骤二：提取预测内容

从 summary 中提取预测信息

**预测内容结构**：
```markdown
## 📈 走势预测

### 短期预测（1-3个月）
- **预测方向**：⬆️ 上涨
- **目标价位**：3.60元
- **概率分布**：上涨70%，震荡20%，下跌10%
- **置信度**：高
- **预测日期**：2026-04-26
- **验证日期**：2026-05-26（预计）

### 中期预测（3-6个月）
- **预测方向**：➡️ 震荡上行
- **目标价位**：3.80元
- **概率分布**：上涨60%，震荡30%，下跌10%
- **置信度**：中
```

**提取方法**：
```python
import re

def extract_prediction(content, fund_code):
    """从 summary 中提取预测信息"""
    prediction_data = {}
    
    # 提取短期预测
    short_term_pattern = r"### 短期预测.*?预测方向[：:]([^\n]+).*?目标价位[：:]([\d.]+)元.*?概率分布[：:]([^ \n]+).*?置信度[：:]([^ \n]+)"
    match = re.search(short_term_pattern, content, re.DOTALL)
    if match:
        prediction_data['short_term'] = {
            'direction': match.group(1).strip(),
            'target_price': float(match.group(2)),
            'probability': match.group(3).strip(),
            'confidence': match.group(4).strip()
        }
    
    # 提取预测日期和验证日期
    date_pattern = r"预测日期[：:](\d{4}-\d{2}-\d{2}).*?验证日期[：:](\d{4}-\d{2}-\d{2})"
    date_match = re.search(date_pattern, content)
    if date_match:
        prediction_data['predict_date'] = date_match.group(1)
        prediction_data['verify_date'] = date_match.group(2)
    
    return prediction_data

# 使用
prediction = extract_prediction(content, "003984")
print(prediction)
# {'short_term': {'direction': '⬆️ 上涨', 'target_price': 3.6, ...}}
```

---

### 步骤三：获取实际结果

在验证日期（或之后）的 summary 中找到实际数据

**查找逻辑**：
```python
def get_actual_result(fund_code, verify_date, archive_root="投资新闻归档"):
    """获取验证日期的实际结果"""
    index_path = f"{archive_root}/index.json"
    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)
    
    # 找到验证日期或之后的第一个 summary
    for summary in sorted(index['summaries'], key=lambda x: x['date']):
        if summary['date'] >= verify_date and fund_code in summary['funds_mentioned']:
            file_path = f"{archive_root}/{summary['file_path']}"
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # 提取实际净值
                actual_nav = parse_actual_nav(content, fund_code)
                return {
                    'date': summary['date'],
                    'nav': actual_nav,
                    'file_path': summary['file_path']
                }
    
    return None

def parse_actual_nav(content, fund_code):
    """解析实际净值"""
    pattern = rf"{fund_code}\s*\|\s*([\d.]+)元"
    match = re.search(pattern, content)
    if match:
        return float(match.group(1))
    return None

# 使用
actual = get_actual_result("003984", "2026-05-26")
if actual:
    print(f"验证日期 {actual['date']} 的实际净值：{actual['nav']}元")
```

---

### 步骤四：对比预测与实际

**对比维度**：

#### 1. 方向准确性

**判断逻辑**：
```python
def check_direction_accuracy(predicted_direction, start_nav, actual_nav):
    """检查方向预测是否准确"""
    actual_change = (actual_nav - start_nav) / start_nav
    
    predicted_up = "上涨" in predicted_direction or "⬆️" in predicted_direction
    predicted_down = "下跌" in predicted_direction or "⬇️" in predicted_direction
    predicted_sideways = "震荡" in predicted_direction or "➡️" in predicted_direction
    
    actual_up = actual_change > 0.02  # 涨幅超过2%算上涨
    actual_down = actual_change < -0.02  # 跌幅超过2%算下跌
    actual_sideways = -0.02 <= actual_change <= 0.02  # ±2%内算震荡
    
    if predicted_up and actual_up:
        return "✅ 准确", actual_change
    elif predicted_down and actual_down:
        return "✅ 准确", actual_change
    elif predicted_sideways and actual_sideways:
        return "✅ 准确", actual_change
    else:
        return "❌ 错误", actual_change

# 使用
start_nav = 3.45  # 预测时的净值
actual_nav = 3.62  # 验证时的净值
accuracy, change = check_direction_accuracy("⬆️ 上涨", start_nav, actual_nav)
print(f"方向预测：{accuracy}，实际变化：{change:.2%}")
# 输出：方向预测：✅ 准确，实际变化：+4.93%
```

#### 2. 价格偏差

**计算方法**：
```python
def calculate_price_deviation(predicted_price, actual_price):
    """计算价格偏差"""
    absolute_deviation = abs(predicted_price - actual_price)
    percentage_deviation = absolute_deviation / predicted_price * 100
    
    return {
        'absolute': absolute_deviation,
        'percentage': percentage_deviation,
        'rating': rate_deviation(percentage_deviation)
    }

def rate_deviation(percentage):
    """评级偏差程度"""
    if percentage < 3:
        return "优秀（偏差<3%）"
    elif percentage < 5:
        return "良好（偏差3-5%）"
    elif percentage < 10:
        return "一般（偏差5-10%）"
    else:
        return "较差（偏差>10%）"

# 使用
deviation = calculate_price_deviation(3.60, 3.62)
print(f"价格偏差：{deviation['absolute']:.2f}元 ({deviation['percentage']:.2f}%) - {deviation['rating']}")
# 输出：价格偏差：0.02元 (0.56%) - 优秀（偏差<3%）
```

#### 3. 概率分布验证

**验证方法**：
```python
def verify_probability_distribution(predicted_prob, actual_outcome):
    """验证概率分布的准确性"""
    # predicted_prob: {'up': 70, 'sideways': 20, 'down': 10}
    # actual_outcome: 'up' / 'sideways' / 'down'
    
    if actual_outcome == 'up':
        assigned_prob = predicted_prob['up']
    elif actual_outcome == 'sideways':
        assigned_prob = predicted_prob['sideways']
    else:
        assigned_prob = predicted_prob['down']
    
    return {
        'assigned_probability': assigned_prob,
        'evaluation': '合理' if assigned_prob > 50 else '偏低'
    }

# 使用
predicted_prob = {'up': 70, 'sideways': 20, 'down': 10}
result = verify_probability_distribution(predicted_prob, 'up')
print(f"分配概率：{result['assigned_probability']}% - {result['evaluation']}")
# 输出：分配概率：70% - 合理
```

---

### 步骤五：生成验证报告

**报告模板**：
```markdown
## 🔍 历史预测验证报告

### 预测基本信息
- **基金代码**：003984
- **预测日期**：2026-04-26
- **验证日期**：2026-05-26
- **预测周期**：1个月（短期）

### 预测内容回顾
- **预测方向**：⬆️ 上涨
- **目标价位**：3.60元
- **起始净值**：3.45元
- **概率分布**：上涨70%，震荡20%，下跌10%
- **置信度**：高

### 实际结果
- **验证日期净值**：3.62元
- **实际涨跌幅**：+4.93%
- **实际方向**：上涨 ✅

### 准确性评估

#### 1. 方向准确性
- **预测**：上涨
- **实际**：上涨（+4.93%）
- **结果**：✅ 准确

#### 2. 价格偏差
- **预测价格**：3.60元
- **实际价格**：3.62元
- **绝对偏差**：0.02元
- **相对偏差**：0.56%
- **评级**：优秀（偏差<3%）

#### 3. 概率分布验证
- **预测上涨概率**：70%
- **实际结果**：上涨
- **评估**：合理（高概率事件发生）

### 综合评分
- **方向准确率**：100%（1/1）
- **价格偏差**：0.56%（优秀）
- **概率合理性**：合理
- **总体评价**：⭐⭐⭐⭐⭐ 优秀

### 经验总结
✅ **成功因素**：
1. 准确判断了新能源板块的政策利好
2. 重仓股宁德时代财报超预期
3. 资金持续净流入趋势判断正确

💡 **改进建议**：
1. 无明显问题，保持当前预测方法
2. 可尝试提高目标价精度（本次偏差很小）

---

### 历史预测统计（近6个月）

| 预测日期 | 预测方向 | 实际结果 | 方向准确 | 价格偏差 | 评价 |
|---------|---------|---------|---------|---------|------|
| 2026-04-26 | ⬆️ 上涨 | +4.93% | ✅ | 0.56% | 优秀 |
| 2026-03-15 | ➡️ 震荡 | +1.2% | ✅ | 2.1% | 良好 |
| 2026-02-10 | ⬆️ 上涨 | -2.3% | ❌ | 5.8% | 一般 |
| 2026-01-20 | ⬇️ 下跌 | -3.1% | ✅ | 1.2% | 优秀 |
| 2025-12-18 | ⬆️ 上涨 | +6.5% | ✅ | 3.2% | 良好 |
| 2025-11-25 | ➡️ 震荡 | +0.8% | ✅ | 1.5% | 优秀 |

**统计结果**：
- **方向准确率**：83.3%（5/6）
- **平均价格偏差**：2.4%
- **优秀率**：50%（3/6）
- **整体评价**：预测模型可靠，建议继续使用
```

---

### 步骤六：基于验证结果调整预测模型

**调整策略**：

#### 1. 如果准确率高（>80%）
```
✅ 保持当前预测方法
✅ 可适当提高置信度
✅ 缩小预测区间（提高精度）
```

**示例**：
```
原预测：上涨概率70%，目标价3.60±0.15元
调整后：上涨概率75%，目标价3.60±0.10元（缩小区间）
```

#### 2. 如果准确率中等（60-80%）
```
⚠️ 分析错误原因
⚠️ 调整权重因子
⚠️ 扩大预测区间（降低风险）
```

**示例**：
```
原预测：上涨概率70%，目标价3.60±0.10元
错误分析：低估了政策影响
调整后：上涨概率65%，目标价3.60±0.20元（扩大区间）
增加政策因子权重：0.3 → 0.5
```

#### 3. 如果准确率低（<60%）
```
❌ 重新审视预测模型
❌ 大幅增加预测区间
❌ 降低置信度
❌ 考虑引入新的预测因子
```

**示例**：
```
原预测：上涨概率70%，目标价3.60±0.10元
错误分析：未考虑到市场系统性风险
调整后：上涨概率55%，目标价3.60±0.30元（大幅扩大）
置信度：高 → 低
新增因子：市场情绪指数、VIX恐慌指数
```

---

## 📊 验证指标体系

### 1. 方向准确率

**计算公式**：
```
方向准确率 = 正确预测次数 / 总预测次数 × 100%
```

**评级标准**：
- **优秀**：>85%
- **良好**：70-85%
- **一般**：60-70%
- **较差**：<60%

### 2. 价格偏差率

**计算公式**：
```
价格偏差率 = |预测价格 - 实际价格| / 预测价格 × 100%
```

**评级标准**：
- **优秀**：<3%
- **良好**：3-5%
- **一般**：5-10%
- **较差**：>10%

### 3. 概率校准度

**目的**：验证预测的概率是否合理

**计算方法**：
```
如果预测上涨概率为70%，那么在100次类似预测中，应该有约70次实际上涨
```

**理想状态**：
```
预测概率60-70% → 实际发生率60-70%
预测概率40-50% → 实际发生率40-50%
```

### 4. 置信度匹配率

**目的**：验证"高置信度"的预测是否真的更准确

**计算方法**：
```
高置信度预测准确率 vs 低置信度预测准确率
```

**理想状态**：
```
高置信度准确率 > 中置信度准确率 > 低置信度准确率
```

---

## 🔄 自动化验证工具

提供自动化验证脚本

```python
"""
预测验证自动化工具
位置：skills/investment-news-analysis/scripts/prediction_verifier.py
"""

import json
import re
import os
from datetime import datetime

class PredictionVerifier:
    def __init__(self, archive_root="投资新闻归档"):
        self.archive_root = archive_root
        
    def verify_all_predictions(self, fund_code, months=6):
        """验证指定基金最近N个月的所有预测"""
        predictions = self.find_predictions(fund_code)
        verification_results = []
        
        for pred in predictions:
            result = self.verify_single_prediction(pred, fund_code)
            if result:
                verification_results.append(result)
        
        # 生成统计报告
        report = self.generate_verification_report(verification_results, fund_code)
        return report
    
    def verify_single_prediction(self, prediction, fund_code):
        """验证单个预测"""
        predict_date = prediction['predict_date']
        verify_date = prediction['verify_date']
        
        # 获取实际结果
        actual = self.get_actual_result(fund_code, verify_date)
        if not actual:
            return None
        
        # 提取预测时的净值
        start_nav = self.get_nav_at_date(fund_code, predict_date)
        
        # 计算准确性
        direction_accuracy = self.check_direction(
            prediction['direction'], start_nav, actual['nav']
        )
        price_deviation = self.calculate_deviation(
            prediction['target_price'], actual['nav']
        )
        
        return {
            'predict_date': predict_date,
            'verify_date': actual['date'],
            'predicted_direction': prediction['direction'],
            'actual_change': (actual['nav'] - start_nav) / start_nav,
            'direction_accurate': direction_accuracy,
            'price_deviation': price_deviation,
            'rating': self.rate_prediction(direction_accuracy, price_deviation)
        }
    
    def generate_verification_report(self, results, fund_code):
        """生成验证报告"""
        if not results:
            return "无可用验证数据"
        
        total = len(results)
        accurate = sum(1 for r in results if r['direction_accurate'])
        avg_deviation = sum(r['price_deviation']['percentage'] for r in results) / total
        
        report = f"""
## 🔍 历史预测验证报告 - {fund_code}

### 统计概览
- **验证周期**：{results[-1]['predict_date']} 至 {results[0]['verify_date']}
- **预测总数**：{total}
- **方向准确率**：{accurate/total*100:.1f}% ({accurate}/{total})
- **平均价格偏差**：{avg_deviation:.2f}%

### 详细结果
| 预测日期 | 验证日期 | 预测方向 | 实际涨跌 | 准确性 | 价格偏差 | 评级 |
|---------|---------|---------|---------|--------|---------|------|
"""
        
        for r in results:
            report += f"| {r['predict_date']} | {r['verify_date']} | {r['predicted_direction']} | {r['actual_change']:+.2%} | {'✅' if r['direction_accurate'] else '❌'} | {r['price_deviation']['percentage']:.2f}% | {r['rating']} |\n"
        
        report += f"""
### 模型调整建议
"""
        
        if accurate/total > 0.8:
            report += "✅ 准确率高，保持当前预测方法，可缩小区间提高精度\n"
        elif accurate/total > 0.6:
            report += "⚠️ 准确率中等，建议扩大预测区间，分析错误原因\n"
        else:
            report += "❌ 准确率低，需重新审视预测模型，引入新因子\n"
        
        return report

# 使用示例
verifier = PredictionVerifier()
report = verifier.verify_all_predictions("003984", months=6)
print(report)
```

---

## ⚠️ 注意事项

1. **验证时机**：
   - 必须在生成新预测前执行验证
   - 验证日期应晚于预测日期至少一个完整周期
   - 如验证日期未到，标记为"待验证"

2. **数据完整性**：
   - 确保验证日期的 summary 存在
   - 确保实际净值数据可获取
   - 如数据缺失，补充搜索或标记异常

3. **异常处理**：
   - 识别黑天鹅事件（如疫情、战争）
   - 异常期间的预测可单独标注
   - 不计入常规准确率统计

4. **样本量要求**：
   - 至少5个预测样本才能计算准确率
   - 样本不足时，标注"样本量少，参考性有限"

5. **持续优化**：
   - 每月更新一次验证报告
   - 根据验证结果调整预测参数
   - 记录调整日志，便于回溯

---

**版本**：v1.0  
**最后更新**：2026-05-05  
**维护者**：NagaResst
