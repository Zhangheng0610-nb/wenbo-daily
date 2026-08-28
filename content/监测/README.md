# 行业关注地图监测库

本目录是行业关注地图的独立数据源。地图不再从每天精选的 4—8 条日报反推行业热度。

## 固定监测口径

固定信源池定义在 `automation/governance.py` 的 `MAP_SOURCE_PANEL`：国家文物局、中国文物报、中国考古网、中国博物馆协会、新华网文博、央视网文博。只有这些来源的记录可以进入地区指数。地方政府、博物馆官网和其他 A/B 级媒体仍可用于日报发现、事实核验和编辑补充，但不能直接改变地区排名。

## 每日文件

每天先生成 `YYYY-MM-DD.json`，再从候选中精选日报。文件必须包含：

- `mode`：`operational` 表示正式连续监测；`archive-backfill` 表示历史回溯重建。二者的覆盖度和健康度分开统计。
- `coverage`：六个固定来源逐一登记为 `success`、`no_update`、`partial` 或 `failed`；没有新内容也必须写 `no_update`，不能省略。
- `items`：当天在固定来源上发现的全部文博相关新内容，而不是只写入日报的内容。
- `selectedForDaily`：该条是否被选入当日日报，只用于解释编辑选择，不影响地图是否收录。

单条 `items` 记录使用下面的结构；`date` 是原文发布日期，不是抓取日期：

```json
{
  "recordId": "mon-20260828-ncha-001",
  "date": "2026-08-28",
  "title": "原文标题或忠实压缩标题",
  "sources": [
    {
      "sourceId": "ncha",
      "name": "国家文物局",
      "url": "https://www.ncha.gov.cn/..."
    }
  ],
  "scope": "province",
  "primaryProvince": "四川",
  "relatedProvinces": [],
  "locationTier": "title",
  "locationConfidence": 0.96,
  "themes": ["文物保护"],
  "tags": ["文物保护", "四川"],
  "selectedForDaily": true
}
```

`scope` 只能是 `province`、`national`、`international` 或 `unassigned`。固定来源同一篇原文被其他媒体转载时，不把转载链接写入监测库；如果固定池内另一个来源独立报道同一事件，可以另存一条记录，构建器会合并证据。

`baseline.json` 是迁移时从旧日报地图中筛出的固定信源历史记录。它的覆盖率不可审计，因此只作为过渡样本；网站会明确标注，不能把它解释为同期行业全貌。随着新的完整巡检日累积，7 日、30 日和 90 日窗口会依次达到可比较标准。

历史回溯文件必须使用 `mode: "archive-backfill"`；正式当天逐源巡检必须使用 `mode: "operational"`。`coverage` 条目同步写入相同的 `mode`，不得把回溯的 `success` 或 `no_update` 解释为当日真实运行健康度。

## 记录原则

1. 搜索引擎只负责发现，`url` 必须是固定信源池的原文。
2. 捕获所有符合本站文博范围的新内容，再做日报精选；不得先选 4—8 条、再反填监测库。
3. 同一来源同一 URL 只存一次。后续报道作为新记录写入，由构建器合并为独立事件。
4. 地区记录必须填写唯一 `primaryProvince`；协作或关联地区写入 `relatedProvinces`，不重复计分。
5. 全国政策、行业会议和对外合作用 `scope: national`；纯国际事件用 `scope: international`；二者不参与省份排名。
6. 无法可靠判断发生地的记录不强行归省，使用 `scope: unassigned`，等待后续核查。
