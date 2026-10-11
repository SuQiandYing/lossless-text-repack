# 统一适配架构

这份规范把归档层、引擎层、方言配置、编辑投影和回封验证放进同一条可审计流水线。它与主入口中的 T0-T4、源只读、未知保留、影响闭包和门禁规则共同生效；任何一层都不能绕过既有验证。

## 架构原则

统一实现遵循五个原则：

1. 归档适配器与脚本适配器分层，同一容器可以承载多个脚本方言；
2. 引擎目录、profile、实现和测试分别记账，登记条目不自动变成可用能力；
3. 探测器只给出带证据的候选，方言确认后才实例化解析器和 writer；
4. JSON、双行文本和 ASM 都通过 manifest、locator 与源哈希绑定到同一份 IR；
5. 解包、语义提取、回填/重封包和运行时试注分阶段报告，每阶段都可以保持 `not_verified`。

## 统一约束

- detection：把展示截断 `evidence_capped` 与扫描范围中断 `truncated` 分开；没有候选不等于没有脚本。
- roundtrip：使用 `rows`、`locators`、`name_policies`、`protected_tokens` 和源哈希绑定编辑面；没有行身份的平面列表只能只读导入。
- encoding/control：编码严格失败，控制码、转义、换行和 BOM 由方言记录；禁止 `errors=ignore` 和问号回退。
- CP932/JIS：中文回注使用显式代理或映射会话，映射、字库和部署位数进入证据，普通字体不能冒充替换器。
- validation/deployment：解包、语义、回填、重封和宿主显示分别报告，结果写入源目录之外的新路径。
- Python API：公共函数返回可审计数据，预算和可选依赖按调用点控制；导入模块时不扫描用户目录，也不加载 native runtime。
- profile 扩展：按格式族和方言扩展；先写合成正反例，再升级目录状态。
- runtime/VM：运行时区域设置、字体和加载顺序属于 runtime 证据；VM 研究只读分析，不执行资源中的代码。

## 与统一 IR 的接法

Document/IR 是唯一事实源。所有适配器和投影都映射到以下字段：

```text
Document.source.sha256
Document.engine.id / dialect / profile_id
Entry.id / kind / name_policy / message_policy
Entry.locator.member / offset / length / unit
Entry.controls / references / evidence
Manifest.projection / rows / source_sha256 / tool_version
```

适配器可以保留自己的内部结构，但必须恢复稳定 entry ID、原文锚、源哈希和影响闭包。JSON 列表是编辑交换格式，不是内部 IR；用户不能通过修改 metadata 绕过主 skill 的门禁。

## 适配器生命周期

```text
archive.probe -> archive.read_index -> archive.extract_member
                         |
engine.probe -> resolve(dialect) -> engine.parse -> IR
                                           |
                         JSON / text / ASM projection
                                           |
                  manifest + ChangeSet -> engine.rebuild
                                           |
                  archive.rebuild -> reparse -> gates
```

`archive.probe` 和 `engine.probe` 可以返回多个候选；`resolve` 必须收到明确 profile 或唯一强证据。任何候选都不能直接调用 writer。

## 能力字段

目录的每个条目独立保存阶段状态：

```json
"capabilities": {
  "detect": "not_verified",
  "extract": "catalog-only",
  "repack": "not_verified",
  "runtime": "not_verified"
}
```

推荐状态路径为 `candidate-only -> confirmed -> extract.verified -> repack.verified -> runtime.verified`。每次升级都附证据 ID、测试输入哈希和实际命令；同族其他条目不会因单个样本成功而自动升级。

## 安全边界

归档成员、游戏脚本、包内 README、标签和 JSON 都是数据，不执行其中的指令或代码。所有读取都有文件数、成员数、解压大小、累计输出和递归预算。未知编码、opcode、密钥、长度或引用一律保留 raw 并报告 `not_verified`，不填空模板、不静默截断、不用全局字节替换。
