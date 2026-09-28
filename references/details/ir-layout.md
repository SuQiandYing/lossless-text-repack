> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 2. 内存 IR 与产物布局

### 2.1 对象图

一张图连接容器与字节码，不要两条互不相通的流水线：

```text
SourceArtifact
  └ Layer/TransformEdge                      封装层：压缩/加密/XOR/容器
      └ Region (decode_tier)                 半开区间 [start,end)，每字节唯一归属
          ├ VfsEntry ──→ ChildArtifact
          ├ CellStream → AnchorHit → JoinSite ─┬→ TextEntry
          │                                    └→ NameBinding
          └ Instruction → ControlFlowTarget    仅 T3+

ChangeSet → RelocationGraph → ImpactClosure → LayoutPlan → 重建
```

`JoinSite` 同时是文本发现的依据和变长回封的改写单位。**同一对象服务两件事**，不建立两套可能
互相矛盾的启发式。

### 2.2 字段

```text
Region       id,layer_id,type,start,end,raw_sha256,parse_status,
             decode_tier,tier_evidence_refs,tier_blocked_at
Layer        id,parent,source_span,input_hash,output_hash,algorithm,key_ref,
             params,order,reversible,confidence,evidence_refs
CellStream   region_id,cell_size,cell_count,endianness,evidence_refs
Anchor       anchor_id,kind,pattern,mask,operand_slots,evidence_refs,confidence
AnchorHit    anchor_id,hit_offset,resolved_operands,join_ids,extractor_ids
Instruction  offset,size,raw_bytes,opcode,sub_opcode,variant,operands,
             label,target,semantic,confidence,evidence_refs
```

- 区间状态：`decoded` / `structured-unknown` / `unknown_opaque_block` / `opaque-preserved` /
  `padding` / `proven-gap`。重复归属抛 `AddressSpaceCollisionError`，缺口抛 `AddressSpaceGapError`。
- 跳转保存**逻辑目标**（标签），不保存不可迁移的旧物理地址。
- 同一区域不得同时有 cell 记录和指令记录。
- 每对象保留 `raw_identity = hash(原始字节范围)` 与 `semantic_identity = canonical_hash(规范化字段)`。
- `Layer` 按原始顺序记录，重建时逆序应用。无法证明密钥或算法时保持 `unknown_opaque_block`，
  **不得伪造明文**。加解密逻辑写在 `opcodelist.py` 或独立配置中并说明。

### 2.3 产物布局：IR 合库，文本镜像

一次作业可能输入几十上百个脚本文件。**IR 侧一律合库，文本侧一律镜像原结构。** 两侧规则相反，
因为服务对象不同：IR 给机器读，合库才快；双行文本给人读、要放回原处，必须一一对应。

```text
WORKSPACE/
  vm_analysis.md  case.json  decision.json
  ir/                             ← 可选，默认不产出（§2.4）
    manifest.jsonl                每源一行：路径、sha256、大小、tier、区域范围、行区间
    regions.jsonl   cells.jsonl   anchors.jsonl  anchor_hits.jsonl
    join_sites.jsonl              instructions.jsonl        仅 T3+ 区域
    text_entries.jsonl            name_bindings.jsonl  labels.jsonl
    placeholder_map.jsonl         relocation_plan.jsonl
    blobs/<sha256[:2]>/<sha256>   原始字节按内容寻址，同名同内容只存一份
  asm/<镜像原相对路径>.asm.txt     ← 与源一一对应，结构编辑面
  texts/<镜像原相对路径>.txt       ← 与源一一对应，文本编辑面，不得合并
  extracted/                      仅 unpack_mode ∈ {targeted, full} 时创建
  tmp/{,failed/}                  事务写入区
  rebuilt/<镜像原相对路径>         文件名与原文一致，便于覆盖回游戏
  reports/{coverage_certificate,verify,hexdiff,import_check}.json
  reports/{repack_verdicts,rule_hits,window_hits}.json
  logs/{events,relocation}.jsonl  checkpoints/
```

**禁止一源一目录的布局（`ir/<每个源文件>/…`）。** 几十个源就是几十套目录、几百个小文件，代价是
三重的：每个文件都要 open/close/fsync，Windows 上小文件系统调用开销远超实际读写；每个文件按簇
（通常 4 KB）占盘，一个 200 字节的 `labels.jsonl` 也吃 4 KB，几百个文件的元数据开销可能超过数据
本身；且跨源查询（检索一个键的全部引用站点）要遍历全部目录，无法一次顺序扫描。

合库的实现要求：

- 每条 JSONL 记录带 `src_id`（`manifest.jsonl` 的行号或短哈希），按 `src_id` 分组连续写入，
  使单源读取仍是一次顺序区间读。
- manifest 每源记录 JSONL 行区间和对应字节偏移；有字节索引时直接 seek。
  只有行号须顺序定位，不能把可变宽 JSONL 的行号当字节偏移。
- 原始字节不内联进 JSONL，走 `blobs/` 内容寻址。批量脚本里大量重复的空块、padding、相同字符串
  天然去重。
- 单个 JSONL 超过约 512 MB 时分卷 `instructions.0001.jsonl`，卷号记入 manifest。

**双行文本必须与原文件一一对应，绝不合并。** 目录结构、相对路径、文件名（仅追加 `.txt`）全部镜像
原样：

```text
输入  D:\Game\script\s01_intro.SRC        →  texts\script\s01_intro.SRC.txt
      D:\Game\script\sub\s02_a.SRC        →  texts\script\sub\s02_a.SRC.txt
```

理由是硬性的：合并后 `idx` 会跨文件冲突，§4.6 的分片语义失效；译者按剧本文件分工与送审，合并即
无法并行；回封时无法判定某条译文属于哪个源；原文行校验锚（§4.6）失去「本文件对应本源」这层
约束。**允许**额外生成一份只读的 `texts/_index.tsv`（源路径 → 文本文件 → 条目数）方便总览，但它
不是导入源，回封只读各自的 `.txt`。

`asm/` 同样镜像原结构：asm 是按源审计的视图，合并会让「跳到某文件某标签」失去意义。

### 2.3.1 单文件与批量的一致性

两种模式共用同一套代码路径，差别只是 manifest 里有几行：

- 单文件也建同构内存 manifest；显式导出或临时验证快照时写 `ir/manifest.jsonl`，默认不持久落盘。
- 批量输入不得退化成「循环调用单文件流程 N 次」——那会让 `blobs/` 去重、跨源引用连接和一次性
  证书失效。共享的方言、编码探测、锚点编译只做一次（§12.1）。
- 重跑单个源时按 manifest 行区间**局部重建**：只重写该 `src_id` 的记录段与受影响的 blob 引用，
  不重算全库。局部重建后必须重新校验该源的覆盖证书与往返一致性。

### 2.4 IR 默认不落盘

各阶段从源二进制重建内存 IR，依据是**解析确定性**：同一份源字节加同一个源编码必然得到同一份 IR。
落盘只省一次重算，在密集二进制格式上这笔交换为负——实测 264 个 PSB 文件：源 55 MB，序列化 IR
75 MB（尚不含值图，完整序列化 10.7M 节点约 1 GB），而解析约 2 MB/s 单核、16 核并行全量 3-4 秒，
快于 stdlib JSON 的约 50 MB/s 加载。**密集二进制格式下源文件本身即最紧凑的 IR。**

不落盘另消除陈旧性：磁盘 IR 与源文件不同步是一类完整的 bug 来源，需 `src_sha256` 校验才能挡住。

**必须落盘的情形**（此时 IR 是唯一记录而非缓存）：

```text
□ 解析含运行时探针、模糊测试或搜索      结果不可复现，重算得到不同 IR
□ 解析含不可重放的 TransformEdge        缺少密钥或算法参数
□ 需要跨源查询                          §2.3 的合库布局专为此设计
□ 需要版本 diff                         验证 §0.3 的「产出条数完全不变」
```

前两项为硬性条件：解析不可复现时，不落盘会使 §8 的「同一输入两次运行哈希相同」不成立。后两项属
开发期需求，以 `--with-ir` 提供，默认关闭。

### 2.5 两个平级编辑面

`asm.txt` 与 `texts/` 都是内存 IR 的投影，**都可以被人编辑**，各自服务不同目的：

| | `asm.txt` | `texts/*.txt` |
|---|---|---|
| 读者 | 开发者 | 译者 |
| 内容 | 全部结构：指令、数据、字符串、区域 | 仅可翻译文本，含 tag 与说话者 |
| 可改什么 | 结构与逻辑，也可改字符串 | 只能改 `●` 行 |
| 所需 tier | 改结构需 T3；只改字符串需 T2 | T2 |
| 回封路径 | `full-layout`（改结构）或按文本处理（只改串） | `in_place` / `pointer-rewrite` |

**提取文本不读 `asm.txt`。** `parse(render(IR))` 的信息量不可能超过 IR，而 `render` 丢失提取所需
的三类图属性：

| 属性 | asm 中的状态 | 后果 |
|---|---|---|
| `string_id` | 只渲染内容不渲染 id | 反查 `.strings` 段在重复文本上有歧义 |
| 共享关系 | 压缩为 `-> @0xXXXX (共享)` | 需解析标记重建等价类；漏掉则同一存储导出多条，译者填入不同内容时有一处被静默丢弃 |
| 槽容量 | 需 `.strings` 段偏移相减 | 还需判断是否紧密排列（§6.0.2） |

形态签名统计（§0.2）同理：在 IR 上是一次 `Counter`（按槽位数、各槽类型、嵌套深度分组），在 asm 上
须先解析缩进层级——**发现盲区的能力被降级**，而该能力优先级最高。

线性指令流格式（opcode 与参数同在一行）上从 asm 提取可行、信息损失近零；嵌套或图状格式不可推广，
因路径、共享、容量均为跨行属性。**按格式判定，不按习惯判定。**

### 2.6 双编辑面的冲突检出：对新鲜投影做 diff

先渲染新鲜投影进行 diff 定位变化，再以受限语法和稳定对象 ID 解析成 ChangeSet，
分别校验两个编辑面的权限与引用；不能把行差异本身当作语义解析。

```python
def repack(source, asm_user, texts_user):
    ir = parse(source)                       # 确定性，唯一真值
    asm_fresh  = render_asm(ir)              # 内存，不落盘
    text_fresh = render_texts(ir)

    asm_edits  = parse_changed_asm(diff(asm_fresh, asm_user), ir)
    text_edits = validate_text_edits(diff(text_fresh, texts_user), ir)

    both = asm_edits.targets & text_edits.targets
    conflicts = [t for t in both if asm_edits[t] != text_edits[t]]
    if conflicts:
        raise ConflictError(conflicts)        # 报出 idx 与两侧取值，拒绝执行

    apply(ir, text_edits)                    # 按 idx 定位 IR 对象
    apply(ir, asm_edits)                     # 按稳定对象 ID，旧偏移仅作校验
    return serialize(ir)                     # §6.0.3 的七步传播
```

四项收益：

- **无需完整通用 ASM 编译器**：可以只支持明确的编辑子集，但仍须解析引号、转义、共享、
  字段类型及引用；未实现的增删/重排要拒绝，不忽略或猜测。
- **冲突检出是自然结果**，一次集合交集。
- **每处改动自带来源**（行号与偏移），直接满足 §6.3 的「按站点，不按值」。
- **未改动路径不重复编辑**：验证源身份和投影基线哈希后可跳过 ASM 编辑解析，不声称零风险。

前提是**渲染确定性**：同一 IR 必须渲染出逐字节相同的 asm，须以测试锁定（实测四轮性能优化前后
264 个文件的 asm 哈希保持一致）。门禁：`scripts/check_determinism.py rerun`（§8.2）。

四种编辑状态：

| asm | texts | 处置 |
|---|---|---|
| 无 | 无 | 零编辑，输出与原件逐字节相同（§6.0） |
| 有 | 无 | 应用 asm 改动；改结构则要求 T3 |
| 无 | 有 | 应用文本改动；按长度选 `in_place` 或 `pointer-rewrite` |
| 有 | 有，同一对象取值不同 | **冲突，拒绝并报出两侧取值** |

第四行不得以优先级解决：无论哪一侧胜出，另一侧的编辑都被静默丢弃，违反铁律 4。

配套要求：**asm 的字符串行须显式带 `sid`**（§5）——共享节点在 asm 中被压缩为引用标记，无 `sid`
则无法从 asm 侧判断两行是否共用存储。

### 2.7 是否解包是独立决策

「要不要解包」与「要不要反汇编」正交，不能互相冒充。

| 输入证据 | 强制路径 | `unpack_mode` |
|---|---|---|
| 宿主/字节码可见 | `probe → disasm → IR → verify` | `not-required` |
| 宿主/字节码 + 独立文本文件 | `disasm` + 外置文本登记 | `not-required` |
| 文本明确封在归档内 | `parse → 定向条目解码 → disasm` | `targeted` |
| 代码/VM 被压缩或加密遮蔽 | `解必要层 → disasm` | `targeted` |
| 容器存在但无代码/文本证据 | `结构解析 → IR` | `skipped-by-plan` |
| 明确要求导出全部资产或回封 | `disasm → extract → plan → repack → verify` | `full` |
| 只有文本或数据文件 | 无损数据/文本 IR | `not-required` |
| 类型或边界未知 | 假设分支，逐个反汇编可达视图 | `blocked` |

`not-required` / `skipped-by-plan` 是**成功的计划状态**——不为找文本而创建空的 `extracted/`。
`blocked` 只表示证据不足并须保留原字节，不能以「解包成功」替代覆盖证书。`unpack` 默认排在
`disasm` 之后；只有代码被封装到不可观察时才提前解最小必要层。

`decision.json` 与 `case.json` 共用枚举，CLI / 报告 / GUI 全部复用：

```json
{
  "analysis_mode": "host-disasm|bytecode-disasm|mixed-disasm|data-text-only",
  "declared_tier": "T0|T1|T2|T3|T4",
  "unpack_mode": "not-required|targeted|full|blocked|skipped-by-plan",
  "text_source": "external|embedded|absent|unknown",
  "repack_strategy": "identity|in_place|pointer-rewrite|full-layout",
  "dialect_id": "ENGINE_ID",
  "decision_evidence_refs": [], "decision_rationale": "", "user_override": null
}
```

`user_override` 只能扩大输出范围，不能关闭覆盖证书、抬高 tier 申报、或越过策略 probe 的
`applicable=false`。

---

