> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 10. 报告纪律

- 分别报告 `byte_coverage`、`structural_coverage`、`tier_coverage`、`instruction_coverage`、
  `roundtrip_identity`、`tag_source` 分布。`heuristic` 与 `unresolved` 的条目数**必须单列**。
  每层给出 `min_tier` 与 `declared_capabilities`。
- 禁用「拆出来了」「大概是」「差不多完整」「应该能回封」。
- **`T1` 不得表述为「已完成全量反汇编」**；「部分文件成功」不得表述为字节完备可逆重构完成。
- 合规表述示例：「T1 cell-stream 覆盖 100%，零编辑往返一致，未申报指令语义。」「T2，已定位 1,284
  个调用锚点，锚点间保持 cell-stream。」
- 交付时说明已完成阶段、产物路径、方言与工具版本、资源限制、未决假设、**未执行的阶段**。
- 交付清单里必须含 `README.md`（§0.4）与 `vm_analysis.md`，且 README 的报错清单与代码实际抛出的
  错误码一致。缺 README 的交付按未完成处理——工具能跑但没人知道怎么用，等于没交付。
- 范围未明确时给编号选项：提级区域、深挖unknown、运行时probe、导出、回封或checkpoint。
  已授权的完整操作连续完成，阶段仍可独立重跑，不用隐藏Run-All扩大范围。

---

以上 §10 及之前各节是**工程纪律**，面向实现者与报告。§11 是**使用者界面**，两者要求不同：内部
必须严格分级与留证，界面必须简单到不懂逆向的人也能用完。

---

