---
name: investment-news-analysis
description: 持仓监控与量化调仓建议系统。面向多持仓组合，收集新闻、生成每日日报、验证预测并输出组合级建议。适用于：分析整体持仓情况、收集市场新闻、生成日报、跟踪组合强弱。❗ 单个持仓逻辑校验与具体调仓建议请使用 single-holding-adjustment SKILL；单基金深度研究请使用 fund-deep-research SKILL。
---

> ⚠️ **免责声明**：本工具仅供个人学习和信息整理使用，所有分析内容均不构成任何投资建议。投资有风险，入市需谨慎，请依据自身判断做出投资决策。

> 📌 **书写规范**：所有报告、预测、验证表格中提及基金时，必须写成“基金名称(代码)”。禁止只写代码，禁止把代码写在名称前面。

> 🚫 **事实纪律（最高优先级，不得违反）**：
> 1. 只能引用实际搜索、抓取或归档到本地的信息。
> 2. 缺失数据必须明确写缺口，不能用估算值或猜测补齐。
> 3. 不得虚构盘中涨跌、第三方观点、个股层行情跟踪、成交量数据。
> 4. 不能把没有确认的数据混入日报主结论。
> 5. 每个预测或建议都必须同时交代支持证据、风险/反向证据、信息边界。

# 投资新闻收集与预测分析

## 核心定位

这是一个面向**当前持仓组合 / 多持仓基金**的日报与建议系统，负责四件事：

1. 先围绕政策、市场行情与量级、宏观建立当天判断框架，再按需补充基金本身信息。
2. 基于前一交易日确认数据生成每日 summary。
3. 验证更早日报中的短期预测，并据此修正当前判断。
4. 生成当日投资建议 HTML 归档页面。

> ❗ **边界说明**：本 SKILL 不做单基金深度研究，不负责输出成体系的深度研究框架、建仓打分和长篇情景推演。如需深度研究单只基金，请使用 `fund-deep-research` SKILL。
>
> 单个持仓的逻辑正确性校验、单持仓调仓建议、单持仓独立报告，请使用 `single-holding-adjustment` SKILL。

## 三份主规范

执行本 skill 时，以下三份文档是唯一主规范：

1. [reference/daily-summary-template.md](reference/daily-summary-template.md)
日报结构、时间视角、章节职责、Markdown 骨架。

2. [reference/prediction-verification.md](reference/prediction-verification.md)
短期预测与历史预测验证的唯一规则来源。

3. [reference/investment-advice-report-20260517-guide.md](reference/investment-advice-report-20260517-guide.md)
HTML 投资建议报告的结构、写法与组件规范。

其他参考文档只提供补充流程或实现细节，不再单独定义另一套日报或建议结构。

## 执行协议

| 阶段 | 必读参考 | 本阶段必须产出 |
|------|---------|---------------|
| 画像约束前 | `投资者行动/投资者画像.md` | 黑名单、风险偏好、工具边界 |
| 当日新闻前 | `scripts/cn_finance_news.py` | 当天 `raw_data/finance_news.json` |
| 搜索前 | [reference/archiving.md](reference/archiving.md) | 当日归档目录、单条摘要字段、去重规则 |
| 定量数据前 | `scripts/fetch_market_momentum.py` | 前一交易日官方净值、ETF 收盘、北向单日、持仓快照 |
| 历史读取前 | [reference/historical-data.md](reference/historical-data.md) | 历史 summary 提取、最近可比较基准读取、持仓变化对比 |
| 预测前 | [reference/prediction-verification.md](reference/prediction-verification.md) | 历史预测验证、信息充分性检查 |
| HTML 输出前 | [reference/investment-advice-report-20260517-guide.md](reference/investment-advice-report-20260517-guide.md) + `reference/investment-advice-report-20260517-template.html` | 符合模板结构的完整 HTML 页面 |

## 阶段零：画像与边界约束

每次开始前必须读取 `投资者行动/投资者画像.md`，确认：

1. 黑名单过滤。
2. 仅推荐场外基金或 ETF 联接基金。
3. 新方向必须有明确政策支持。
4. 用户当前风险偏好和既有套牢经历。

## 阶段一：定量数据与历史上下文

### A. 读取历史数据

搜索前必须读取：

1. `投资新闻归档/index.json`
2. 与当前持仓相关的近期 summary
3. `投资者行动/持仓情况.md`

用途：

- 对比持仓份额变化
- 提取更早的短期预测
- 提取上一轮有效判断与边界

细则见 [reference/historical-data.md](reference/historical-data.md)。

### B. 再跑定量脚本

先运行 `scripts/fetch_market_momentum.py`。

统一口径：

- `--date YYYY-MM-DD` 代表生成这一天的日报。
- 日报中的基金净值、ETF、北向单日，一律截到**前一交易日**。
- 北向近 7 天窗口保留，但窗口终点同样是前一交易日。
- 不使用估值，不使用分析日当天 ETF spot，不使用当天北向单日数据。

推荐调用方式：

```bash
python3 skills/investment-news-analysis/scripts/fetch_market_momentum.py --date YYYY-MM-DD --output 投资新闻归档/YYYY-MM/YYYY-MM-DD/raw_data/market_momentum_YYYY-MM-DD.json
```

### C. 准备当天 `finance_news.json`

找到当天目录下已经有：

`投资新闻归档/YYYY-MM/YYYY-MM-DD/raw_data/finance_news.json`

这是前一天由 `scripts/cn_finance_news.py` 自动运行后把结果落到当天 `raw_data/finance_news.json`。
注意：不要自己运行cn_finance_news.py做重复的工作，直接使用已有的 JSON 文件！！！

## 阶段二：搜索与归档

搜索顺序以 [reference/search-strategy.md](reference/search-strategy.md) 为准。主链路固定为：

1. 先读今天 `raw_data/finance_news.json`
2. 先搜政策面
3. 再搜市场行情面和量级新闻
4. 最后搜宏观面

主链路完成后，再按需要补：

1. 基金本身信息
2. 同类基金横向比较
3. 政策新方向雷达

每轮搜索后立即归档：

- 外部信息到 `item_summaries/`
- 脚本输出到 `raw_data/`

基金本身信息搜索放在后面，且只是补充项；没有新增基金直接新闻不影响主链路判断，只需简要记录“无新增直接新闻”即可，不必为此扩大搜索范围。

## 阶段三：预测与验证

短期预测和历史预测验证一律遵守 [reference/prediction-verification.md](reference/prediction-verification.md)。

硬规则：

1. 历史预测验证只能来自更早 summary 的 `短期预测` 章节。
2. 做新预测前必须先完成历史预测验证。
3. 做新预测前必须先通过信息充分性检查。
4. `短期预测` 必须是独立章节，方便下一轮提取验证。

## 阶段四：建议生成

本阶段目标是把前文信息压缩成**当日动作判断**。

必须按以下顺序完成：

1. 验证上一轮判断是否有效。
2. 复核当前持仓状态。
3. 结合横向比较确认强弱排序。
4. 给出逐基金状态复核与操作建议。
5. 生成今日关注要点。

如需逐基金动作细化，写法以日报模板第八章和 HTML 指南第四章为准，不得另起一套字段体系。

## 每日 Summary 输出要求

每日 summary 的标准结构、章节职责、模板骨架统一见：

- [reference/daily-summary-template.md](reference/daily-summary-template.md)

执行时直接按该模板落章。

最低要求：

1. 核心指标表必须包含 `持有份额` 和 `当前持有金额`。
2. 如检测到份额变化，必须写 `持仓变化检测`。
3. `复盘与风险雷达` 必须服务动作判断，不能只是前文重复。
4. `今日关注要点` 必须面向分析日当天，不写成机械的“明日关注”。
5. 数据附录必须写出 `item_summaries_count`、主要 raw_data 文件名、关键缺口和反向证据。

## 投资建议 HTML 输出要求

每次执行分析后，必须生成独立 HTML 页面：

`投资者行动/持仓分析与建议/投资建议报告_YYYYMMDD.html`

HTML 规则以 [reference/investment-advice-report-20260517-guide.md](reference/investment-advice-report-20260517-guide.md) 为准。

这里只保留最低要求：

1. summary 只生成 Markdown，不生成 HTML。
2. 投资建议正式归档只认 HTML 页面。
3. 第二章必须先解决“今天先看什么”。
4. 第四章必须一只基金一张卡片。
5. 第七章必须保留固定摘要表供后续机器解析。
6. 基金名单只能来自 `投资者行动/持仓情况.md`，不得靠正文手写回忆补全。
7. 交付前必须逐一对账：目录子链接数、第四章基金卡片数、第七章摘要表行数，三者都必须与当前持仓基金数量一致。
8. 交付前必须逐一对账基金名称：目录、第四章卡片标题、第七章摘要表第一列，必须全部使用与持仓文件一致的“基金名称(代码)”全称。
9. 如果使用 `investment-advice-report-20260517-template.html`，必须填充 `fund_cards_json`，让正文基金名称自动挂载悬浮卡片；悬浮卡片最少包含净值、总金额、占比三项。

### HTML 交付前强制校验

HTML 生成完成后，未通过以下校验不得交付：

1. `持仓情况.md` 中每一只当前持仓基金，都在目录、第四章和第七章各出现且只出现一次。
2. 第四章基金卡片数必须等于当前持仓数，禁止少卡、并卡、漏卡。
3. 第七章摘要表基金行数必须等于当前持仓数，禁止沿用上一版摘要表。
4. 若启用模板悬浮卡片，fund_cards_json 条数必须等于当前持仓数，且 `full` 字段必须与持仓文件中的“基金名称(代码)”完全一致。
5. 若任何一项数量或名称对不上，优先修正 HTML 和数据映射，不得带着缺口继续输出结论。

## 最低交付线

一次完整运行至少应产出：

1. `item_summaries/`
2. `raw_data/`
3. `summary_YYYY-MM-DD.md`
4. `投资建议报告_YYYYMMDD.html`

并满足：

1. 完整 8 持仓日报默认不少于 8 条单条归档。
2. 普通完整日报默认不少于 6 条单条归档。
3. raw_data 中必须存在可回溯单条归档的结构化 JSON。
4. 若无新增基金直接新闻，必须归档反向证据。

## 参考文档

- [reference/archiving.md](reference/archiving.md) - 归档与单条摘要规则
- [reference/daily-summary-template.md](reference/daily-summary-template.md) - 日报模板
- [reference/historical-data.md](reference/historical-data.md) - 历史读取规范
- [reference/prediction-verification.md](reference/prediction-verification.md) - 预测验证规范
- [reference/search-strategy.md](reference/search-strategy.md) - 搜索层次与范围
- [reference/position-management.md](reference/position-management.md) - 组合内逐基金状态整合
- [reference/nav-analysis.md](reference/nav-analysis.md) - 净值分析与触发线辅助方法
- [reference/directory-structure.md](reference/directory-structure.md) - 目录结构
- [reference/investment-advice-report-20260517-guide.md](reference/investment-advice-report-20260517-guide.md) - HTML 说明

## 日常操作顺序

1. 读取投资者画像。
2. 读取历史 summary、最新持仓。
3. 运行 `fetch_market_momentum.py`。
4. 准备当天 `raw_data/finance_news.json`。
5. 按主链路完成政策、市场行情与量级、宏观搜索，再决定是否补基金本身信息。
6. 分层搜索并即时归档。
7. 执行历史预测验证和信息充分性检查。
8. 生成每日 summary。
9. 生成投资建议 HTML 页面。

---

**版本**：v4.1  
**最后更新**：2026-05-22  
**维护者**：NagaResst
