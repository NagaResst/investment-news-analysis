# Investment News Analysis Skill

> ⚠️ **免责声明**：本工具仅供个人学习和信息整理使用，所有分析内容均不构成任何投资建议。

这是一个面向**当前持仓组合 / 多持仓基金**的新闻归档、日报生成、预测验证与建议归档系统。

单个持仓的逻辑校验和具体调仓建议，不再由这个 skill 主负责，请使用 `single-holding-adjustment`。

## 核心输出

1. 每日 Markdown 日报：`投资新闻归档/YYYY-MM/YYYY-MM-DD/summary_YYYY-MM-DD.md`
2. 单条信息摘要：`item_summaries/`
3. 原始结构化数据：`raw_data/`
4. 投资建议 HTML 页面：`投资者行动/持仓分析与建议/投资建议报告_YYYYMMDD.html`

## 核心口径

- 基金数据使用前一交易日官方净值。
- ETF 使用前一交易日收盘日线。
- 北向使用前一交易日单日数据，近 7 天窗口保留，但终点仍是前一交易日。
- 不使用估值，不使用分析日当天 ETF spot，不使用当天北向单日数据。

## 三份主规范

1. [reference/daily-summary-template.md](reference/daily-summary-template.md)
每日 summary 的唯一模板来源。

2. [reference/prediction-verification.md](reference/prediction-verification.md)
短期预测与历史预测验证的唯一规则来源。

3. [reference/investment-advice-report-20260517-guide.md](reference/investment-advice-report-20260517-guide.md) + `reference/investment-advice-report-20260517-template.html`
HTML 建议报告的唯一写法来源与唯一页面骨架。生成 HTML 时必须直接基于模板文件填充，禁止脱离模板另写一套页面结构。

## 最短工作流

1. 读取 `投资者行动/投资者画像.md`
2. 准备当天 `raw_data/finance_news.json`
3. 运行 `scripts/fetch_market_momentum.py`
4. 读取历史 summary 与最新 `持仓情况.md`
5. 先跑政策、市场行情与量级、宏观主链路，再按需补基金本身信息
6. 外部信息写入 `item_summaries/`，脚本输出写入 `raw_data/`
7. 执行历史预测验证与信息充分性检查
8. 生成每日 summary
9. 基于 `reference/investment-advice-report-20260517-template.html` 生成投资建议 HTML 页面

## 相关文档

- [SKILL.md](SKILL.md) - 主指令文件
- [reference/archiving.md](reference/archiving.md) - 归档规则
- [reference/search-strategy.md](reference/search-strategy.md) - 搜索范围与顺序
- [reference/historical-data.md](reference/historical-data.md) - 历史读取规范
- [reference/directory-structure.md](reference/directory-structure.md) - 目录结构

---

**最后更新**：2026-05-27
