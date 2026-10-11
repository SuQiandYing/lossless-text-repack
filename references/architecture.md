# 统一架构

## 变换链

```text
source snapshot
  -> archive adapter (bytes -> members)
  -> engine adapter (members -> structured script)
  -> dialect/profile (version, encoding, opcode and layout rules)
  -> Document IR
  -> projection (JSON / ASM / audit report)
  -> manifest + ChangeSet
  -> engine writer
  -> archive writer
  -> reparse + byte/semantic/runtime checks
```

每层有自己的输入、输出、预算和证据。归档层只负责成员边界、压缩、加密、索引和封包；引擎层负责脚本记录、VM 指令、字符串池、姓名/正文语义和控制码；投影层负责编辑交接。一个 `.pak` 能解包，不表示其中的脚本能提取；一个脚本能导出，不表示变长译文可重封；一个文件能重封，也不表示目标宿主会加载。

## 适配器职责

### ArchiveAdapter

```text
probe(source, budget) -> [ArchiveCandidate]
read_index(source, candidate) -> ArchiveIndex
extract_member(source, index_entry, budget) -> Member(bytes, locator, opaque)
build_archive(original, replacements, plan) -> bytes
```

必须保留记录顺序、物理顺序、间隙、尾部、不透明索引字段、压缩方法和包间关系。`probe` 的扩展名或弱魔数只能增加候选分数，不能授权 `build_archive`。

### EngineAdapter

```text
probe(member, context) -> [EngineCandidate]
parse(member, dialect, budget) -> Document
export(document, projection) -> ProjectionBundle
plan_changes(document, translated_projection) -> ChangeSet
rebuild(document, changes, policy) -> RebuiltMember
```

`parse` 必须给每个可编辑项稳定 ID、原文锚、locator、编码和控制码；未知区进入 `opaque_spans`。`rebuild` 只接受本 adapter 生成且源哈希匹配的 ChangeSet。不要让 detector 直接返回 writer 或让投影字段反向决定方言。

### RuntimeProfile

运行时 profile 只记录部署路径、加载优先级、位数、字体/字库和实测入口。它不能由静态结构推断；没有真实加载记录时保持 `runtime=not_verified`。

## 状态模型

每个引擎都分别记录：

```json
{
  "detect": "not_verified|candidate-only|confirmed|ambiguous",
  "extract": "not_verified|analysis|verified",
  "repack": "not_verified|verified",
  "runtime": "not_verified|verified"
}
```

`verified` 必须绑定证据 ID 和测试输入哈希。`catalog-only` 是 profile 的总状态，表示只登记了资料，不能调用任何 writer。`partial` 只能用来描述有明确边界的阶段组合，不要把它当作成功的同义词。

## 证据优先级

1. 当前样本的结构约束、版本字段、交叉引用和重新解析结果；
2. 当前 adapter 的合成反例、零编辑往返和变长回填测试；
3. 固定提交的格式源码/文档及符号出处；
4. 文件名、扩展名、目录名和可读字符串等弱线索。

证据相互冲突时保留竞争假设，输出 `ambiguous`，要求人工选择 dialect。禁止按注册顺序“第一个命中”静默选 writer。

## 引用闭包

变长编辑的影响闭包至少包括：文本长度字段、字符串池、记录起点、绝对/相对指针、跳转目标、索引排序、压缩后的成员大小、外层包索引和校验。只有证明所有相关站点已更新，才允许 `repack=verified`。未知引用必须让该操作停在 `not_verified`，而不是用全局整数替换。
