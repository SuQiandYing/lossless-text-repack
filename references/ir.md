# IR、Locator 与 ChangeSet

统一 IR 是内存中的审计模型，不是把所有引擎强行压成同一种文件格式。未理解的字节仍以 `opaque_spans` 保留；只有被证据授权的字段可编辑。

## Document

```json
{
  "schema": "lossless-text-repack.ir/1",
  "source": {"path": "original/scene.bin", "sha256": "...", "size": 1234},
  "engine": {"id": "kirikiri", "dialect": "kag-v2", "profile_commit": "local"},
  "entries": [],
  "opaque_spans": [],
  "metadata": {"encoding": "cp932", "newline": "crlf"}
}
```

`source.sha256` 是解析和回填的绑定，不是可由用户编辑的字段。`engine.dialect` 必须由证据和 profile 明确给出。`metadata` 只能保存不影响身份的方言数据；长度、指针和控制码仍放到 locator 或 entry 的结构字段。

## Entry

```json
{
  "id": "scene.bin:dialogue:000042",
  "kind": "dialogue",
  "name": "角色",
  "name_policy": "writable|context|absent|readonly",
  "message": "原文",
  "message_policy": "writable|readonly",
  "locator": {"member": "scene.bin", "offset": 812, "length": 18, "unit": "bytes"},
  "source_text": "原文",
  "raw_hex": "...",
  "controls": [{"kind": "ruby", "raw": "...", "span": [2, 8]}],
  "references": ["scene.bin:pool:17"],
  "evidence": ["ev-0042"]
}
```

`id` 是稳定对象身份，不按导出行号生成。`kind` 至少区分 `dialogue`、`narration`、`choice`、`name`、`command` 和 `opaque`。正文和姓名分别有策略；旁白不能因为投影里没有 `name` 就被当成缺失。`raw_hex` 只用于审计锚，不允许用户把它当作编辑接口。

## Locator

locator 指向成员、物理偏移、长度、编码单元和可选的引用站点。它不是全局搜索模板。偏移/长度必须在源文件范围内，重叠只有在 profile 明确共享资源时才允许；共享资源的不同逻辑使用必须可以表达为独立引用，否则拒绝变更。

## Manifest

manifest 至少包含：源清单和哈希、engine/dialect、导出投影、行到 entry 的映射、name policy、控制码摘要、原始编码、工具版本、预算、以及每个阶段的 `status`。manifest 是导入门禁的一部分，不能通过手改 manifest 绕过错误。

## ChangeSet

```json
{
  "schema": "lossless-text-repack.changes/1",
  "source_sha256": "...",
  "document_id": "...",
  "changes": [
    {"entry_id": "...", "expected_source": "原文", "message": "译文", "name": "译名"}
  ]
}
```

导入时要求 entry 集合、顺序锚、原文、姓名策略、控制码和源哈希都匹配。相同物理字符串被多个逻辑 entry 共享时，必须由 profile 指明是“共享替换”还是“按引用克隆”；两个不同译文不能使用最后写入获胜。

## 能力等级

`T0` 只证明区间和字节保留；`T1` 证明单元边界；`T2` 证明字段/文本和引用；`T3` 证明完整指令边界；`T4` 证明控制流与必要语义。变长回填需要受影响字段至少达到 T2，VM 指令编辑通常需要 T3/T4。无关未知区不自动否决局部编辑，但影响闭包内的未知引用必须阻止回封。
