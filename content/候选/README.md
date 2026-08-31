# 日报候选账本

本目录只记录日报编辑链路发现的广域候选，不属于行业关注地图的 `content/监测/` 固定六源监测库。

- `discoverySource` / `discoveryUrl`：用于发现线索的渠道，不自动代表最终证据资格。
- `evidenceSources`：支持事实并展示给读者的原始来源；新稿只接受 A/B 级证据。
- `decision`：`selected`、`rejected`、`deferred` 或 `needs_verification`。
- `decisionReason`：结构化编辑理由；被拒候选也要留下，便于回答“发现了什么、为什么没发”。

官方机构微信公众号只有在账号身份、机构归属、官网反向确认和原创关系均核验后，才可登记为机构一手证据；未登记的 `mp.weixin.qq.com` 仍按线索处理。

每日 broad discovery 的主动扫描、查询记录和去重审计保存在 `content/发现/YYYY-MM-DD.json`；当天候选账本通过 `discoveryAuditPath` 引用该审计文件。发现来源与最终证据来源始终分开。
