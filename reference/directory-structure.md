# 目录结构详解

## 完整目录结构

```text
投资新闻归档/
├── index.json
├── YYYY-MM/
│   └── YYYY-MM-DD/
│       ├── summary_YYYY-MM-DD.md
│       ├── item_summaries/
│       │   ├── 001_xxx.md
│       │   └── ...
│       └── raw_data/
│           ├── finance_news.json
│           ├── market_momentum_YYYY-MM-DD.json
│           └── ...

投资者行动/
└── 持仓分析与建议/
    └── 投资建议报告_YYYYMMDD.html
```

## 核心文件

### 1. `index.json`

位置：`投资新闻归档/index.json`

作用：

1. 记录所有 summary 的元数据。
2. 提供历史检索入口。
3. 支持预测验证与历史读取。

建议最小结构：

```json
{
  "last_updated": "2026-05-20T08:30:00",
  "total_summaries": 10,
  "funds_tracked": ["003984", "011609"],
  "summaries": [
    {
      "date": "2026-05-20",
      "file_path": "2026-05/2026-05-20/summary_2026-05-20.md",
      "funds_mentioned": ["003984", "011609"],
      "key_events": ["工信部继续强化智能网联新能源汽车扩容"],
      "item_count": 9,
      "created_at": "2026-05-20T08:30:00"
    }
  ]
}
```

### 2. `summary_YYYY-MM-DD.md`

位置：`投资新闻归档/YYYY-MM/YYYY-MM-DD/summary_YYYY-MM-DD.md`

作用：

1. 汇总当日所有重要信息。
2. 提供核心指标速览、横向比较、验证、复盘和当日动作准备。
3. 保持 Markdown 单文件归档，不额外生成 HTML 页面。

唯一模板入口：

- [daily-summary-template.md](daily-summary-template.md)

### 3. `item_summaries/`

位置：`投资新闻归档/YYYY-MM/YYYY-MM-DD/item_summaries/`

作用：

1. 存储每条高/中关联信息的独立摘要。
2. 支持后续引用、去重、反向证据补录。

命名规范：

```text
001_标题.md
002_标题.md
```

### 4. `raw_data/`

位置：`投资新闻归档/YYYY-MM/YYYY-MM-DD/raw_data/`

作用：

1. 保存脚本输出与搜索原始数据。
2. 为日报和 HTML 页面提供溯源依据。

常见文件：

```text
finance_news.json
market_momentum_YYYY-MM-DD.json
analysis_snapshot_YYYY-MM-DD.json
```

说明：

1. 外部搜索得到的新闻、政策、市场和宏观信息，优先写入 `item_summaries/`。
2. 只有脚本产出的结构化文件进入 `raw_data/`。

### 5. `投资建议报告_YYYYMMDD.html`

位置：`投资者行动/持仓分析与建议/投资建议报告_YYYYMMDD.html`

作用：

1. 作为正式建议归档页面。
2. 供后续读取上次建议摘要与持仓份额变化。

唯一结构入口：

- [investment-advice-report-20260517-guide.md](investment-advice-report-20260517-guide.md)

## 每日日报与 HTML 的关系

1. daily summary 只生成 Markdown。
2. 投资建议只生成 HTML 正式归档。
3. HTML 不替代 daily summary，daily summary 也不替代 HTML。

## 生成顺序

1. 先归档单条信息和 raw_data。
2. 再生成 `summary_YYYY-MM-DD.md`。
3. 最后生成 `投资建议报告_YYYYMMDD.html`。
4. 更新 `index.json`。

## 常见错误

1. 把日报写到错误目录层级。
2. 只有 `summary` 没有 `item_summaries/`。
3. 没有保存 raw_data 就直接写总结。
4. 把 HTML 当成日报正文替代物。
