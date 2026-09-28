# 解析、证据与文本发现

这是实施补充，不替代 [完整VM证据](details/vm-evidence.md)、[IR布局](details/ir-layout.md)、
[引用连接](details/reference-joins.md) 与 [声明式方言及代码](details/dialect.md)；对应任务必须同时读取。

适用：未知格式、变体适配、理解深度申报、文本定位或人名绑定。返回 [主流程](../SKILL.md)。

## 目录

- [证据与能力](#证据与能力)：T0–T4、能力闭包、未知区
- [对象图与封装层](#对象图与封装层)：内存 IR、原始身份、边界
- [形态派发](#形态派发)：L1–L3、零命中、多命中
- [文本发现](#文本发现)：inline、引用连接、假阳性
- [人名与分类](#人名与分类)：绑定、三轴、权威来源

## 证据与能力

源字节是最终真值；IR 是给定源、方言、选项和工具版本的解析解释。证据台账记录声明，而非让声明替代源验证。仅有数据容器时写格式分析，不为满足模板强行逆向不存在的 VM。

证据最小字段：`evidence_id, claim, source_hash, source_location, method, observation, counterexamples, limitations`。区分：

- `observed`：可重放的直接观测，如字段读取路径、容器类型标记或执行跟踪。
- `derived`：从已验证结构及明确推导规则得到，链接全部前提。
- `inferred`：统计、外观、邻近等候选解释；不单独授权改写。
- `ambiguous` / `unresolved`：竞争解释或证据不足，保留候选，不任选。

同一解析器产出的两张报表不是两份独立证据。高风险边界、指针语义、长度与校验公式应有独立约束交叉验证；确实只有一种证据时如实声明，不凑数。可靠性来自能反驳错误解释的约束，而不是固定证据条数。

### T0–T4 区域申报

| 层级 | 已证明的性质 | 应保留的数据 | 不能由该层级推出 |
|---|---|---|---|
| T0 `byte-span` | 可读取区间及原字节身份 | 层、`[start,end)`、原始哈希、保留方式 | 内部单元、文本、指令语义 |
| T1 `cell-stream` | 该区域的单元划分 | 单元宽度/数量、目标字节序、对齐证据 | 每个单元是指令或引用 |
| T2 `anchor-resolved` | 已证明的字段/锚点及对象关系 | 结构路径或锚点、槽位、对象与站点证据 | 锚点间完整指令流 |
| T3 `instruction-stream` | 代码区域完整指令边界及操作数模式 | 偏移、长度、opcode、变体、原字节、操作数 | 跳转语义、可达性、运行时等价 |
| T4 `semantic-cfg` | 对所声明范围的控制流与必要语义 | 逻辑标签、边、块、调用/栈效应及未决项 | 任意输入下行为等价 |

对于非字节码数据，T2 可以由结构化字段、长度、类型、父子路径证明；T3/T4 标为不适用，而不是把数据伪装为指令。T0 已能保留字节并完成零编辑往返，不能把 T1 当作复制原字节的必要条件。

区域层级按实际证据申报：一段证据不完整时拆分区域，剩余部分保留 T0，或整体降级，不发明 `T1-partial`。T1 的宽度不能只凭“长度恰可整除”：应结合宿主读取步长、字段布局、已知锚点对齐等约束。T3 要求所申报代码区间无缝、无重叠，不是全文件都必须为代码。

### 能力不是全文件最低层级

每次操作先求 **受影响闭包**：直接编辑对象、共享存储、所有引用、布局、长度/校验、父容器和变换依赖。闭包外的 T0 块可以逐字节保留，不应阻断一个局部已证明的文本修改。反过来，某一区域达到 T4 也不能授权修改闭包中未知的容器指针。

| 操作 | 需要证明的条件 |
|---|---|
| 覆盖与零编辑往返 | T0 可行；所有原字节可重放，所有实际重编码变换可复现 |
| 文本导出 | 目标为已解析文本字段或已证明的引用目标；至少结构级/T2 证据 |
| 原位文本编辑 | 字节边界、编码、容量、终止符与共享关系已知 |
| 指针重定位 | 完整入站引用集合、站点编码、地址基准、可用存储空间及父层依赖已知 |
| 数据布局重排 | 受影响的数据结构、所有引用和封装依赖已知；不强制数据区达到 T3 |
| 指令重排 | 受影响代码有 T3 边界，且所有地址依赖和必要控制流已证明 |
| 控制流改写/指令插删 | 相关闭包满足 T4 语义与约束，适配器明确实现该能力 |

以上是必要条件，不是“达到层级即可执行”的充分证明；策略仍须通过 [probe](rebuilding.md#probe-与-run)。报告同时给出区域 tier 和实际操作能力，勿用全局 `min_tier` 代替闭包裁决。

遇到未知 opcode：先检查前一条长度、操作数分派、宿主处理逻辑（若可用）；不能证明时回到最后验证边界，保留原字节并记录阻断位置。不得把剩余字节批量伪装为单字指令；这只阻断依赖该段理解的能力，不自动否定保留与导出其他已证明区域。

## 对象图与封装层

```text
SourceArtifact → Layer/TransformEdge → Region
  ├ VfsEntry → ChildArtifact
  ├ StructuredField → TextEntry
  ├ Cell/AnchorHit → JoinSite → TextEntry
  └ Instruction → LogicalTarget
TextEntry ↔ StorageIdentity / NameBinding
ChangeSet → ImpactClosure → LayoutPlan
```

最小契约：

```text
SourceArtifact  src_id, relative_path, sha256, size
Layer          layer_id, parent, source_span, transform, parameters,
               input_hash, output_hash, replayability, evidence_refs
Region         region_id, layer_id, start, end, kind, status,
               raw_sha256, decode_tier, evidence_refs, blocked_at
TextEntry      src_id, object_id, idx, storage_id, structural_path,
               raw_span, source, source_encoding, tag, tag_source,
               translate_policy, evidence_refs
JoinSite       join_id, source_layer, owner_object_id, field_id,
               site_offset, width, endianness, address_base,
               key_kind, target_object_id, evidence_refs
```

同一地址空间的字节所有权区间互斥并覆盖可观测输入；对象引用可以共享，但不能把共享字节重复记为拥有者。每个层分别核算覆盖，不能将压缩前后区间混入同一地址空间。同一区域的 cell 与指令记录可存在派生映射，但证书只能选一个拥有者表示，不能重复计数。

保存 `raw_identity` 与规范化 `semantic_identity`，用途不同：前者证明原始字节，后者比较解析结果。长度字段的非最小宽度、不可达槽位、padding、别名和共享子树都可能是必须保留的信息。不能仅凭“解析树语义相同”重建零编辑文件。

封装层按实际顺序登记，重建时逆序恢复。无法证明的加密/压缩块可原样保存；不得伪造明文或声称支持修改。随机 IV、时间戳、压缩参数等非确定性应记录重放材料或明确能力限制。

IR 默认只存在于内存。CLI 门禁需要文件时，可在作业临时目录导出有 `src_sha256 / schema_version / tool_version / dialect_hash / options_hash` 的验证快照，验证后按日志策略清理；这不是默认交付 IR。不可重放的观测应持久保存证据和必要快照，不把缺失的重放材料藏在“缓存”里。

## 形态派发

### 差异分层

| 差异 | 处理机制 |
|---|---|
| L1：布局相同，opcode/调用 ID/编码等值不同 | 方言参数及证据更新 |
| L2：语义相同，平铺/嵌套、槽数或路径不同 | 条目级形态派发 |
| L3：容器、类型系统或封装模型不兼容 | 独立 profile 或显式模型分支，共享可证等价的 core |

依据内部签名、字段布局和形态选择；文件名/扩展名可作为查找线索，不作为证明。并非见到 `if version` 就必须分叉，也不为追求共享把不兼容布局塞入同一解析分支。

对本次提供的语料遍历目标结构，统计槽数、字段类型、嵌套形态、空值与共享情况。报告的是**已提供语料的覆盖**，不是穷尽所有引擎版本。大型/不完整语料若只能抽样，记录抽样范围，不能宣称全量形态覆盖。

### 零命中、多命中都不能静默

```python
matches = [shape for shape in shapes if shape.matches(entry)]
if not matches:
    return UnresolvedShape(signature(entry))
if len(matches) > 1:
    return AmbiguousShape([shape.id for shape in matches])
return matches[0].extract(entry)
```

`matches` 为无副作用纯谓词。不能用声明顺序的“第一个成功”掩盖重叠；若确有优先关系，应给出经过验证的显式消歧规则并记录排除原因。零命中进入 `unresolved`，阻断依赖该条目的完整提取声明；其他独立条目可继续，但整个结果必须呈现部分状态。

每个形态记录：匹配条件、字段/嵌套路径、角色映射、证据、命中数。新形态测试至少覆盖成功、相近但不匹配、零命中、重叠命中及已知旧形态。回归比较的不仅是条数，还包括 `(src_id, object_id, source, tag, bindings)`；修复真实漏提取时允许计数变化，但须有预期差异清单，而非无条件要求数量不变。

跨来源、跨形态样本提高置信度。只有一个来源时如实标注未验证外推范围，不为凑数量生成“第二来源”。类别比例、每 KB 条目数等只是异常信号；“已证明有对话却提取零正文”才是与具体期望矛盾的失败。相关门禁见 [验证契约](validation.md)。

## 文本发现

### 两条合法路径

1. **结构直接证明（inline）**：类型化容器字段、已解析长度前缀字符串、指令的已证明 inline 操作数。保存父对象、字段/索引路径、字节边界、角色证据，不强制虚构跨文件 Join。
2. **引用连接（referenced）**：已证明的字段存储某目标对象的身份键，建立可追溯 JoinSite。发现、上下文与重定位复用同一关系，不建立两套互不一致的定位逻辑。

原始字节扫描、字符串搜索、特征码搜索可用于**提出假设与定位研究位置**，也可辅助审计漏提取；扫描命中本身不成为可导入文本、角色证明或可改写站点。必须将候选提升为上述两种结构关系之一。

引用键可为层内偏移、显式 ID、已证明算法的路径哈希、表序号与表基址。内容相同不等于对象相同：文本内容/内容哈希不能自动成为引用身份键。

### 引用证据与碰撞

等值只是候选筛选。验证站点的字段类型/宽度、对齐、地址空间与基准、目标边界、锚点或容器上下文，并对分布异常做解释。密度阈值是方言诊断，不能单独授权或否决一条有直接结构证据的引用。单一提取器如有充分结构证明即可成立；两个共享同一假设的提取器“投票一致”也不能替代证据。

| 情况 | 处理 |
|---|---|
| 一个目标、一处引用 | 记录该站点，不据此自动推断整张表 |
| 一个目标、多处引用 | 正常共享关系，全部入站站点参与相关重定位 |
| 目标无已知引用 | 记 `unreferenced`；保留对象，不自动删除，也不声称绝对不可达 |
| 同一键匹配多个目标 | 收窄层/容器/键域；仍歧义则阻断该改写 |
| 字面整数恰与偏移相同 | 非站点保持原样，并纳入值碰撞回归用例 |

表格推断需表头、计数、步长、边界等结构证据；单调命中序列或连续零字节只是线索。多个提取器对同一字段给出不同解释时保留双方与来源，不采用先到先得。

## 人名与分类

### 人名绑定是独立关系

```text
NameBinding  binding_id, msg_object_id, name_object_id / virtual_name,
             method, confidence, candidates, evidence_refs
```

证据优先使用显式名字 ID，其次已证明的参数槽序号/调用结构；仅物理相邻或外观相似为 `inferred`。低强度候选不得覆盖已证明关系；两条直接证据冲突时也不能只凭优先级掩盖，应报告歧义。旁白可有明确“无说话者”状态，不强制绑定名字。

绑定歧义时不输出确定说话者；保留候选供审阅。虚拟名字来自运行时 ID/固定代码时记录其来源；未实现回写就保持只读，不伪造成可编辑独立字符串。共享字符串改一处影响哪些消息必须由 `storage_id`/别名图决定。

### 三轴独立

| 字段 | 值与用途 |
|---|---|
| `tag` | 闭集 `name / msg / choice / label / ui / system / ruby / misc`；表达角色 |
| `tag_subtype` | 方言细分，如 `menu-button / asset-path`；不暗中改变核心策略 |
| `tag_source` | `structural / anchor / binding / heuristic / user / unresolved`；表达证据来源 |
| `translate_policy` | `translatable / length-locked / review-required / frozen`；表达允许的编辑 |

`misc` 表示角色尚未确定，应保留候选及 `unresolved` 计数，不能借兜底分类隐藏未知量。结构已证明为文本但角色不明的条目可以导出为待审，不因此自动获准改写。

**策略与标签的权威来自本次重新解析的 IR / 已验证方言。** 编辑文件中的 `tag`、`policy`、`off` 是需要核对的投影，不能反向放宽 IR 限制。人工确认若被支持，应是明确、可追溯的审阅记录，由独立的允许规则消费；写一行 `policy=translatable` 不构成授权。

典型默认：消息/名字/选项等可见文本可翻译，内部标签冻结，未决角色待审。格式串、资源名、字体名是否冻结由实际用途证明，不靠字符串长相。冻结条目仍可导出用于审阅，未修改自然通过，修改则拒绝。

上下文派生的标签可保存为 `derived_tag`，不覆盖结构标签、冻结策略或 tier。报告独立列出 `heuristic` 与 `unresolved` 数量；文本编辑契约见 [投影与编码](projections.md)。
