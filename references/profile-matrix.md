# Profile 与方言组织

Profile 是容器和脚本格式族的稳定身份；dialect 描述同一 profile 下由版本、编码、opcode、字段布局或文本规则决定的具体形态。游戏名称只作为样本标签，不能单独决定解析器或 writer。

## 概念映射

| 责任 | 位置 |
|---|---|
| VM/证据台账 | `references/architecture.md` 与适配器报告 |
| IR、稳定对象和引用 | `references/ir.md` |
| 文本/ASM 双编辑面 | `references/projections.md` |
| 变长回封、事务和重定位 | `references/roundtrip.md` |
| 门禁、报告和验证 | `references/validation.md` |
| 方言与跨版本 | `catalog/engines.json`、`profiles/` 和本目录 |

T0-T4、源只读、未知保留、失败隔离和字节级验证始终是共同规则。归档/引擎分层、投影契约和候选检测只是这些规则的具体组织方式，不能降低所需证据等级。

## 适配器边界

- `python/archives` 对应 ArchiveAdapter：成员边界、索引、压缩、加密和封装顺序。
- `python/engines` 对应 EngineAdapter：脚本记录、VM 指令、字符串池、姓名/正文语义和控制码。
- `text_input`/`text_output`、manifest、locator、source hash 和 no-overwrite 约定组成统一编辑交接。
- detection、validation、roundtrip 和 provenance 共同决定阶段状态，不能把静态登记当成运行证据。
- JIS/CP932 会话、控制码和姓名策略属于公共投影约束；具体编码仍由方言证据决定。

目录中的 95 个 profile 条目是可追踪的资料索引，不是随条目附带的 parser。条目默认 `catalog-only`，只有当前目录包含 parser/writer、合成正反例、零编辑往返、变长回填和对应证据时，才可以升级相应阶段。不同来源的许可证和改动记录必须分别保存，不能用一个总许可证掩盖实现来源。

## 迁移现有适配器

先把旧函数包成 adapter，生成 Document/Manifest，再逐步替换内部实现。旧的平面 JSON 若没有 sidecar，应只读导入并要求重新导出；不能猜行号、文件名、姓名槽或共享字符串身份。旧结果目录可以作为 `original/` 输入，但不能当作新的源哈希。

## 版本与形态选择

1. 容器头、版本号、字段布局和封装层决定 profile；
2. 锚点、调用 ID、编码和索引约束决定 dialect；
3. 同一文件内逐条统计形态签名，再选择 entry shape；
4. 多个候选同时成立时返回 `ambiguous`，保存反例和被拒候选，要求显式选择。

参数不同使用同一 profile 的不同 dialect；语义结构不同使用同一解析器的并列 shape；容器或类型系统真正不兼容时才拆分 profile。新增形态必须带正例、负例、未命中统计和旧样本回归结果。
