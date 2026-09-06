---
name: lossless-text-repack
description: "脚本字节码与归档的无损逆向重建工具规范。内存 IR 为解析真值且默认不落盘，asm 与双行文本为两个平级可编辑投影；引用连接式文本发现、人名绑定、文本三轴标注、分级理解申报（T0-T4）、文本变长回封与长度计算、站点级重定位、双编辑面 diff 与冲突检出、两按钮 GUI 交付、批量合库与性能、零突变逐字节验证。自包含，不依赖其他 skill。"
---

# 脚本字节码与归档的无损逆向重建

## 目标

把样本当成可审计的编译管线：

```text
源二进制（唯一真值） → 封装层 → 区域 → 内存 IR → asm.txt / 双行文本 → 重建 → 验证
```

三个正交指标，永不混用：

```text
byte_coverage       每字节唯一归属        硬门禁，恒为 1.0
roundtrip_identity  未编辑重建逐字节一致  硬门禁，恒须通过
decode_tier         结构理解的深度        分级申报，决定允许申报的能力
```

前两个不可协商。第三个按证据申报：**T1 + 往返一致就是合格交付；虚报 T3 不是。**
「全量反汇编」的门禁内容是如实申报深度，不是必须做到指令级。

## 六条铁律

1. **只读源**。样本复制进工作区并记 SHA-256/MD5；写入走临时文件 → 校验 → 原子改名。
2. **IR 是解析真值，但不是持久产物**。内存 IR 由源二进制解析得出，`asm.txt` 与 `texts/` 是它的
   两个**平级投影**，均可被人编辑（§2.5）。提取文本只读内存 IR，不读 `asm.txt`。跨文件的文本与
   引用发现只走已证明的引用连接（§3）；**严禁**对原始字节做正则、特征码或旁路文本扫描。
3. **改写按站点，不按值**（§6.3）。
4. **不静默**。编码兜底、歧义任选、窗口截断后继续、策略 run 失败后自动降级——全部禁止。
5. **阶段隔离**。无默认 Run-All；失败即写 checkpoint 并停该分支。每个阶段只产出自己那一类产物，
   不得顺带生成下一阶段的产物（§11.5）——否则该阶段无法被单独重跑，失败也无法被单独定位。
6. **覆盖率不等于提取正确**（§0）。全部门禁通过、往返逐字节一致，仍可能一条正文都没提取到。
   产出为空或只剩单一类别时，必须当作失败而不是"该样本就这样"。

---

## 0. 首要前提：全部门禁通过仍可能完全错误

本节限定后续所有条款的适用范围。

实测：一份工具在 264 个文件上达到 `byte_coverage=1.0`、零编辑往返逐字节一致、严格证书通过、
158 项测试通过。换同引擎另一部作品后提取出 418 条文本——414 条人名、4 条 UI、**正文 0 条**，
无报错无告警，往返一致性依旧成立。原因：该作品将台词置于多语言嵌套结构（`texts[i][1][0][1]`），
工具仅读平铺槽位，而该槽位值为 `null`。

现有门禁全部无效，且各有其结构性原因：

| 门禁 | 无效原因 |
|---|---|
| `byte_coverage=1.0` | 字节归属与语义理解无关 |
| `roundtrip_identity` | 不修改必然逐字节相同，提取为空反而最易通过 |
| `decode_tier` | 描述结构深度，不描述**变体是否穷举** |
| 覆盖证书 | 证明区间与哈希，不证明目标对象已全部命中 |
| 单元测试 | 语料同源，共享同一盲区 |

### 0.1 产出合理性门禁（Output Sanity Gate）

除字节门禁外，必须增设针对**产出内容**的检查。以下任一条命中即判定为失败并转人工确认，
不得以「样本特性」为由放行：

```text
□ 任一类目标产出为 0（例如剧本类样本抽出 0 条正文）
□ 产出高度倾斜（单一类别占比超过 95%，其余接近 0）
□ 抽出条数与容器内同类对象数量数量级不符
  （例：容器有 1,413 个字符串、607 个对话条目，却只抽出 4 条正文）
□ 更换同引擎样本后，每千字节产出量变化超过一个数量级
□ 已知必然存在的结构（对话、选项）在该样本中一条未命中
```

对剧本类输入，第一条尤为关键：**含对话的作品不可能提取到 0 条正文**。此约束并非启发式推测，
而是领域确定性事实，因此已编码为门禁：`scripts/check_output_sanity.py`（§8.2）。

### 0.2 结构变体必须穷举，不得采样

`ParseHypothesisLattice`（见术语表）原用于格式未知时保留竞争假设。上述案例表明它还有第二项用途：
**同一格式内部的形态变体**。步骤如下：

1. 遍历全部语料统计目标结构的**形态签名**（槽位数、各槽类型、嵌套深度），不得仅抽查前若干文件。
2. 每个未见过的签名必须显式处理或显式记为 `unresolved`；**禁止**回落到已知分支后静默产出空结果。
3. 拿到新样本时先跑签名统计再跑提取。签名分布与已知语料不同，即为提取逻辑可能失配的信号。

该案例中的签名统计定位了问题：607 个条目均为 5 槽形态，语言项中 388 个为 3 槽、219 个为 5 槽，
与已知作品的 6/9 槽形态完全不同。**先统计形态，再实现提取逻辑。**
门禁：`scripts/check_shapes.py`（§8.2）。

本节规定「必须穷举」，§7.1 规定「如何在一套代码内兼容多个形态」——同引擎多版本的实现机制见该节。

### 0.3 跨样本验证是硬要求

基于单一语料的测试套件会将盲区固化为「通过」。因此：

- 至少在**两个不同来源**的样本集上验证，且这两个集合的形态签名分布必须不同。
- 仅有一个来源时，须明确记录「未进行跨样本验证」并列为已知风险，不得省略。
- 新增形态支持后，须回归验证既有样本的产出条数**完全不变**（实测为 66,334 条前后一致），
  以证明新分支未覆盖既有路径。

### 0.4 交付必须含 README.md

工具交付时必须随附一份 `README.md`，读者是**拿到工具的人**（翻译者、汉化组、几个月后的自己），
不是实现者。缺它的后果不是"文档不全"，而是前面所有严格性白费：使用者不知道 `○` 行不能改、不知道
译文留空会被拒、不知道超长时该怎么办，于是绕过工具直接改二进制，或者把报错当 bug 反馈。

**内容按「使用者会遇到的顺序」组织，不按模块结构组织：**

```text
□ 这是什么、能对哪些文件用           一两句话，含已验证的样本范围与版本
□ 装什么依赖                         Python 版本；无第三方依赖就明说
□ 怎么跑                             GUI 双击 / 拖放 / 命令行三种，各给一条可复制的命令
□ 产出的文件都是什么                 texts/ asm/ rebuilt/ reports/ 各一行
□ 双行文本怎么改                     给一个真实的两行示例，说明 ○ 只读、● 可改
□ 改完怎么装回去                     含"装回去之后要把 rebuilt/ 里的文件复制到哪"
□ 报错怎么办                         把工具实际会报的错逐条列出，每条给处置办法
□ 已知限制                           不支持的样本、未解决的结构、tier 不足导致做不到的操作
```

三条硬要求：

- **报错清单必须与代码实际抛出的错误一一对应。** §6.1 的 `reason_code` 与导入校验的拒绝码
  （`SOURCE_ANCHOR`、`LENGTH_OVERFLOW`、`EMPTY_TRANSLATION` 等）都是使用者会真实看到的字符串，
  每条都要在 README 里能查到含义与处置。列出代码里不存在的错误，或漏掉会抛出的错误，都算缺陷。
- **不写内部概念。** `decode_tier`、`unpack_mode`、`repack_strategy`、`collision_class`、
  `JoinSite` 一律不出现——这与 §11.1 对界面文字的要求一致，README 是界面的延伸而非规范的摘要。
  确实需要说明能力边界时，用后果表述：「这个样本只支持等长替换，译文不能变长」。
- **已知限制不得省略。** 写明"暂不支持哪些"比让使用者自己撞上去更省时间，也避免把限制当成 bug
  上报。§0.3 若未做跨样本验证，此处必须如实写出。

两份文档都在交付清单里，缺任一份都不算交付完成：

| | `README.md` | `vm_analysis.md` |
|---|---|---|
| 读者 | 拿到工具的人 | 维护者、审阅者 |
| 回答 | 怎么用、报错了怎么办 | 每个方言数值凭什么这么定 |
| 写内部概念 | 不写 | 必须写，且带证据等级 |
| 缺了会怎样 | 没人会用，或用错 | tier 申报失去依据（§1.2） |

## 交付物

四个 Python 文件 + 两份文档：

| 文件 | 职责 |
|---|---|
| `opcodelist.py` | 声明式方言：opcode、锚点、容器布局、加解密、文本规则、窗口常量 |
| `disassembler.py` | 源二进制 → 内存 IR → `asm.txt` + 覆盖证书；另暴露文本提取入口产出 `texts/` |
| `assembler.py` | 源二进制 + `asm.txt` 与 `texts/` 的改动 → 重建二进制（§2.6） |
| `run_gui.py` | 两按钮图形界面，只调用上面三个模块的函数（§11） |
| `vm_analysis.md` | VM 逆向分析与证据台账，为前四者共同的唯一真值源 |
| `README.md` | 面向使用者的说明书（§0.4） |

两份文档不可互相替代，分工见 §0.4。

`disassembler.py` 暴露两个可分别调用的入口（渲染 asm、提取文本），对应界面上「输出文本」的两个
勾选项；两者输入均为源二进制，互不依赖（§11.5）。`assembler.py` 不从 `asm.txt` 完整重建，而是
重新解析源二进制并应用两个编辑面的 diff——因此无需编写完整的 ASM 语法解析器（§2.6）。

三种入口，产出必须完全一致（同一输入 → 同一 IR、同一证书哈希）：

| 入口 | 用法 | 输出位置 |
|---|---|---|
| 拖放 | 文件/文件夹拖到 `disassembler.py` 图标上；`texts/` 或 asm 拖到 `assembler.py` 上 | 见下 |
| 命令行 | 显式指定输入/输出/编码/策略，支持目录批处理 | `-o` 指定，缺省同拖放 |
| GUI | `run_gui.py`，面向无逆向经验的使用者，两个按钮完成全流程（§11） | 界面可修改，缺省同拖放 |

**输出位置统一为一条规则**：在**输入的共同父目录**下建立 `output/`，内部按 §2.3 布局
（`ir/ asm/ texts/ rebuilt/ reports/`）。输入为单个文件时，其父目录即共同父目录。禁止在源文件所在
位置产生散落文件，禁止覆盖原件（铁律 1）。三种入口均遵守此规则，GUI 与命令行仅可修改 `output/`
的位置。

- Python 3.11+，使用 `struct`/`pathlib`/`hashlib`；大文件按块或 mmap 处理，内存占用为
  `O(block_size)`。禁止以 `.sh`/`.ps1`/`.js` 作为实现交付，禁止通过 `subprocess` 外置核心解析逻辑。

---

## 1. VM 分析与理解深度申报

反汇编前必须逆向目标 VM 并产出 `vm_analysis.md`，它是后续一切解析与重建的唯一真值源。内容：
体系结构（堆栈/寄存器）、指令编码风格、解码流程（如何切分操作码与操作数、大小端、对齐、
定长/变长）。

### 1.1 Opcode 字典

每条至少：`opcode`、`byte_pattern`+`mask`、`length`（定长值或变长计算规则）、`operand_schema`
（`imm8`/`imm16`/`strref`/`rel_offset`/`reg`）、`sub_opcode`（位置 + 全部合法子码语义）、
`variants`（同主码因操作数格式而语义不同时的全部变体及切换条件）、`evidence_refs`、`confidence`。

变长指令必须明确边界判定依据。子码必须全部枚举并路由到正确解释器，**不得当无关数据丢弃**。

### 1.2 decode_tier

Tier 单调：申报 `T3` 意味着同时满足 `T0..T2`。每个区域必填 tier 与**至少两条独立证据**
（`T0` 可空），两条中至少一条为 `observed` 或 `derived`。

| Tier | 已证明 | 必须保存 | 不得声称 |
|---|---|---|---|
| T0 `byte-span` | 区间边界与原始字节 | `start,end,raw_sha256,status` | 任何内部结构 |
| T1 `cell-stream` | 定长单元切分 | `cell_size,cell_count,endianness` | 单元语义、指令边界 |
| T2 `anchor-resolved` | 锚点已识别定位 | `anchor_kind,pattern+mask,offsets,operand_slots` | 锚点间的指令边界 |
| T3 `instruction-stream` | 完整指令边界，无缝无重叠 | `offset,size,raw_bytes,opcode,variant,operands` | 可达性、跳转语义 |
| T4 `semantic-cfg` | 基本块、跳转目标、调用图、栈效应 | `labels,targets,basic_blocks,cfg_edges` | 运行时行为等价 |

没有 `T1-partial`。切分或锚点解析不完整就降一级，剩余字节记 `unknown_opaque_block` 并在证书中
单列。

**T1 不是「猜它 4 字节一组」。** 两条独立证据从下列取：长度对 `cell_size` 整除且不整除即解析
失败（不得截断或补齐）；已知锚点值只出现在对齐位置；宿主以该步长读取；引用键只在对齐位置命中。
T1 已足以逐字节往返——每个 cell 原样写回即恢复原流，是合法交付物。

### 1.3 能力矩阵

允许申报的能力由参与操作的**所有**区域的最低 tier 决定：

| 能力 | 最低 tier | 附加前置 |
|---|---|---|
| 覆盖证书 + `byte_coverage=1.0` | T0 | 每段 `raw_sha256` 可从源复算 |
| 零编辑逐字节往返 | T1 | 全部 cell/opaque 可原样重写 |
| 文本发现与双行文件导出 | T2 | 来源为已解析结构或已证明的引用连接 |
| `in_place` 回封（等长） | T2 | 目标编码字节数 ≤ 原槽容量 |
| `pointer-rewrite` 回封（变长） | T2 | 全部引用槽已定位并经独立约束二次验证 |
| `full-layout` 重排 | T3 | 全部指针/跳转/表容量/校验依赖已解析 |
| 控制流改写、指令插删 | T4 | 影响闭包无 `unresolved` |

反向也是硬规则：**tier 不足即不得执行该能力。** 用户要 `full-layout` 而只到 T2 时，正确响应是
给 `pointer-rewrite` 或说明缺哪类证据，不是降低验证标准。

### 1.4 未定义 Opcode：排查后降级

遇到 `vm_analysis.md` 未记录的疑似操作码，按序排查：

1. 回溯宿主可执行文件，查找该字节序列的直接处理逻辑。
2. 检查邻近指令边界是否因长度误判产生连锁偏移——当前「opcode」可能实为前一条指令操作数的一部分。
3. 修正定义回写 `vm_analysis.md`，重跑全量反汇编。

三步都不成立时：**回溯到最后一条已验证指令，记录并降级；不猜测后继续，也不判定案件失败。**

```text
tier_blocked_at: {attempted: "T3", settled: "T2", offset: 0x1A40,
                  last_verified_instruction_offset: 0x1A2C, reason: "UNDEFINED_OPCODE"}
```

`tier_blocked` 不为空**不影响**严格成功。指令对象只存在于 T3+ 区域；T1/T2 用 cell 与锚点记录——
**不得**为填满指令表把 cell 伪装成单字长度的「指令」。

### 1.5 跳转标签化

跳转/条件跳转/调用/返回都提取解析后的目标，在 asm 中生成符号标签（`loc_00001200`），指令引用
标签而非硬编码偏移。文档中明确偏移基准（相对指令起始 / 指令末尾 / PC）与地址空间范围。变长文本
重写导致指令流长度变化时**必须通过标签重定位**。

### 1.6 窗口常量必须显式有据

前瞻长度、块最大跨度、扫描窗口是**方言参数**。每个在 `opcodelist.py` 中有名字、带 `evidence`
（实测最大跨度加余量，记录实测值）、带 `on_exceed`（`stop` 放弃候选 / `blocked` 需更多证据）。
**不得静默截断后继续。** 触达上限次数写 `window_hits.json`——不为零说明可能正在丢弃真实结构，
必须暴露。优先用结构终止条件（显式开/闭调用）替代固定窗口。

---

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
- `manifest.jsonl` 每源记录它在各 JSONL 中的**行区间** `[start_line, end_line)`，单源操作直接
  seek 到区间，不必解析整库。
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

- 单文件输入也建 `ir/manifest.jsonl`（一行），产物布局与批量完全相同。
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

两个编辑面同时可改，必须解决"改动如何合并"与"冲突如何检出"。做法是**渲染一份新鲜投影再 diff**，
而非解析用户文件：

```python
def repack(source, asm_user, texts_user):
    ir = parse(source)                       # 确定性，唯一真值
    asm_fresh  = render_asm(ir)              # 内存，不落盘
    text_fresh = render_texts(ir)

    asm_edits  = diff(asm_fresh, asm_user)   # 仅用户实际改动的行
    text_edits = diff(text_fresh, texts_user)

    both = asm_edits.targets & text_edits.targets
    conflicts = [t for t in both if asm_edits[t] != text_edits[t]]
    if conflicts:
        raise ConflictError(conflicts)        # 报出 idx 与两侧取值，拒绝执行

    apply(ir, text_edits)                    # 按 idx 定位 IR 对象
    apply(ir, asm_edits)                     # 按行首偏移定位 IR 对象
    return serialize(ir)                     # §6.0.3 的七步传播
```

四项收益：

- **无需完整的 ASM 解析器**：只解析改动的若干行，行首偏移映射回 IR 对象即一次字典查找；转义、
  引号、共享标记的歧义处理全部不必编写。
- **冲突检出是自然结果**，一次集合交集。
- **每处改动自带来源**（行号与偏移），直接满足 §6.3 的「按站点，不按值」。
- **未改动路径零风险**：只改文本时 asm 分支整个跳过。

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

## 3. 引用连接：文本发现的唯一合法机制

铁律 2 禁止旁路扫描，这节是替代品。**严禁用正则从二进制抓文本**，所有信息经结构化方式提取——
即引用连接：一个可判定的等值关系，A 文件某位置存的值等于 B 中某结构对象的身份键。

```text
JoinSite(A, site_offset, site_width) --value--> JoinKey <--identity-- Target(B, object_id)
```

典型实例：脚本流中某 4 字节字，其值等于文本容器中某条目的起始偏移。这条关系一旦证明，同时给出
三项结果：**发现**（哪些条目是活文本，哪些是死条目）、**上下文**（引用点周围的锚点决定角色，
替代外观猜测）、**重定位**（引用点集合就是变长回封必须回填的槽位集合）。

```text
XrefJoin  join_id, source_layer, source_artifact_hash,
          site_offset, site_width, site_endianness, site_tier,
          key_kind, key_value, target_layer, target_object_id,
          anchor_ref, confidence, collision_class, rewrite_policy, evidence_refs
```

存为 `ir/join_sites.jsonl`。asm 注释、双行文件的 `refs=`、重定位计划都从它投影。

### 3.1 合法的键

`entry_offset`（目标在其层内的起始偏移）、`entry_id`（容器显式存储的 ID/索引）、
`virtual_path_hash`（算法已证明）、`table_ordinal`（已证明定长表中的序号 + 表基址）。

禁止用文本内容、内容哈希、前缀或长度作键。禁止把「值落在合理范围内」当命中——范围是筛选条件，
不是等值关系。

### 3.2 假阳性控制

值相等是必要非充分条件。标 `derived` 至少还需：**对齐**（站点偏移符合该区域已证明的 cell
对齐）、**范围**（键值指向某条目的 start 而非内部）、**锚点上下文**（站点被已识别锚点包裹）、
**密度**（站点数与目标条目数之比可解释；比例异常说明键域太宽，必须收窄）。

只满足「值相等 + 对齐」的标 `inferred`：可进候选集，但**不得驱动回封改写**，也不得据此往双行
文件加条目。

### 3.3 碰撞分类

| `collision_class` | 判定 | 处置 |
|---|---|---|
| `unique` | 恰一个站点 | 可作 `derived` 证据；可作定位锚点 |
| `multi-site` | 多个站点 | 合法且常见；全部站点进重定位集合 |
| `unmatched` | 目标存在但无站点 | 标 `unreferenced`；**不得**因此删除或跳过该条目 |
| `ambiguous-key` | 一个站点值同时匹配多个目标 | 键定义有缺陷，先收窄，不得任选 |

`unique` 是可靠的定位锚点，但**用它反推整张表的布局需要额外证据**。若用「从锚点向后按序扫描
匹配」建表，必须同时满足四条：表内每键都有站点、站点偏移单调递增、步长符合已证明的对齐、表尾
之后不再出现同类命中。任一条不成立就降级为逐条独立连接，不宣称存在表。

**禁止用特征字节序列（如连续零字节）猜测引用表位置**——那属于旁路扫描。

### 3.4 锚点上下文 → 角色

`Anchor.kind` 由方言声明，至少区分 `call`（带被调用者标识的调用点）、`param-set`（连续参数槽
写入块）、`push`（立即数入栈）、`table-slot`（定长表槽位）。推导链必须完整可追溯：

```text
JoinSite → AnchorHit → anchor.callee_id / slot_ordinal → RoleCandidate
```

链存在时角色可标 `derived`；不存在时为 `unresolved`——**不得**改用外观规则把它提升。外观规则的
唯一合法位置：在**已由锚点证明为文本参数**的多个候选间做次级消歧，结果标 `inferred` 并保留
全部候选。

### 3.5 多提取器共识

同一批锚点可由多个提取器实现（如「调用前连续立即数」与「参数块 + 邻近调用」）：各自记
`extractor_id` 独立产出；按 `(anchor_offset, join_ids, resolved_operands)` 去重，**不按先到
先得覆盖**；对同一锚点给出不同槽位解释时产生 `ambiguous` 并保留双方；合并结果记 `agreed_by`，
仅被一个提取器命中的锚点置信度不得高于 `inferred`。

---

## 4. 文本：三轴标注、人名绑定、编码

### 4.1 三轴分离的理由

单个 `tag` 字段同时承担三项职责：文本的**角色**、判断的**来源**、以及**是否允许编辑**。
三者合并只有两种退化结局：为表达「可见 UI 文本」不断增加 tag 取值，导致取值集合发散；
或为维持固定取值集合，把证据不足的条目并入 `msg`。拆分如下：

```text
tag              结构角色，闭集        tag_source       判断来源与强度
tag_subtype      方言自由细分          translate_policy 可否编辑及约束
```

四者独立取值。`tag=misc` + `policy=review-required` 是合法组合，且比硬标成 `msg` 诚实。

### 4.2 轴一：tag（闭集，八个）

| `tag` | 定义 | 判定依据 |
|---|---|---|
| `name` | 说话者名，绑定到某条 `msg` | `NameBinding` 存在 |
| `msg` | 正文、旁白、独白 | 锚点证明为消息调用的文本参数 |
| `choice` | 玩家可见选项 | 锚点证明位于选项构造块内 |
| `label` | 脚本标签、分支锚点、跳转目标名 | 锚点证明为标签注册调用的参数 |
| `ui` | 界面可见的非对话文本 | 锚点证明为 UI 绘制/注册调用的参数 |
| `system` | 引擎或系统提示 | 锚点证明为系统消息调用的参数 |
| `ruby` | 注音、furigana | 结构上从属于另一条文本 |
| `misc` | **角色未证明** | 无——必须带 `tag_source=unresolved` 与候选列表 |

任何方言都不得扩展这八个。`misc` 不是兜底类别，而是「角色未证明」的显式标记。

更细区分写 `tag_subtype`（自由字符串，如 `menu-button`、`internal-anchor`、
`font-family-name`、`asset-path`）。**跨方言的通用逻辑（文本校验、回封、证书、UI 过滤）只读
`tag`，不读 `tag_subtype`**——这样方言能随意细分而不让核心契约发散。取值集合由方言声明并写入
清单；导入时校验在集合内，但不校验语义。

### 4.3 轴二 tag_source / 轴三 translate_policy

| `tag_source` | 含义 | 最弱证据 |
|---|---|---|
| `structural` | 容器结构直接给出角色（独立名字表、带类型字段的条目） | `observed` |
| `anchor` | 由锚点命中与槽位序号推出 | `derived` |
| `binding` | 由人名绑定等成对关系推出 | `derived` |
| `heuristic` | 在锚点已证明的候选间用外观规则消歧 | `inferred` |
| `user` | 人工指定，记操作者与时间 | `observed` |
| `unresolved` | 无可用证据 | — |

- `heuristic` **只能**在已由锚点或结构证明存在文本参数的候选间做次级选择。不得从零发现条目，
  不得把 `unresolved` 直接提升为具体 `tag`。
- **不设兜底规则。** 一条「其余都算 misc」的规则会让 `unresolved` 计数永远为零，从而隐藏
  「尚有多少条目未被理解」这一关键指标。
- 报告必须给出 `tag_source` 分布，`heuristic` 与 `unresolved` 单独列出，不得并入其他计数。

| `translate_policy` | 语义 | 导入校验 |
|---|---|---|
| `translatable` | 应当翻译 | 目标编码可表示、占位符完整、长度按回封模式校验 |
| `length-locked` | 可翻译但字节长度必须相同 | 额外校验编码后字节数等于原长度 |
| `review-required` | 角色未证明，导出但需人工确认 | 同上，另要求文件显式带确认标记 |
| `frozen` | 不得修改（资源名、内部 ID、字体名、格式串） | 译文行必须与原文行逐字符相同 |

由于导出时译文行预填原文（§4.6），`frozen` 的校验在未编辑时天然通过——它拦的是**改动**，不是
"未填写"。因此 `frozen` 条目照常导出、照常参与 idx 编号，只在被改动时报错。

默认映射（方言可覆盖，覆盖须写入清单并给理由）：

```text
tag ∈ {name,msg,choice,ui,system,ruby} → translatable       tag == label → frozen
tag == misc → review-required           tag_source == unresolved → review-required（覆盖前两条）
```

`frozen` 条目**仍然导出**。这是有意的：翻译者能看到全部条目，才能发现「这条被标 `frozen` 的
实为可见文本」。隐藏条目会让漏译无法被发现。

### 4.4 四个编码字段

职责独立，不得互相推断：

```text
source_encoding  原始字节 → IR 文本        text_encoding  双行文本文件本身（UTF-8/16）
target_encoding  译文写回目标；长度按它算   asm_encoding   asm.txt 视图
```

文本文件用 UTF-8、目标写 CP932 是正常配置。可表示性校验只针对 `target_encoding`。未指定时取
方言声明值，并在 asm 头部以 `.encoding "cp932"` 记录供重建复用。

**不可解码字节禁止静默兜底。** `errors="surrogateescape"`/`"replace"` 会让这些字节在后续任何
一次重新编码中被静默改写且不留证据。核心路径禁用。该条目改为 `parse_status=undecodable`、保留
`raw_bytes` 与 `raw_sha256`、强制 `frozen`、以占位符逐字节呈现。

### 4.5 占位符

普通反斜杠**不是转义前缀**，按脚本文本直接保留。**严禁把 `\xNN` 当十六进制转义，严禁输出原始
十六进制字节注释。** 无法安全显示的字节用大写占位符：

```text
{{([0-9A-F]{2})(:[0-9A-F]{2})*}}
```

- 每个 `XX` 代表一个字节：`{{00}}`、`{{FF:01}}`。适用于控制字符、解码失败字节、Unicode 私用区
  字符；私用区按原始编码字节成组输出（CP932 的 `F0 41` → `{{F0:41}}`）。
- **斜杠、全角空格等可正常显示的字符不得转义成占位符。**
- 记录 `ph_count / ph_bytes / ph_hash / ph_policy`。禁止删除、拆分、改值、改大小写或静默替换
  未知控制码。汇编时占位符直接解析为原始字节（忽略编码边界），不产生多余字符。

### 4.6 双行文本文件

```text
# TEXT/2 ir=IR_VERSION tool=TOOL_VERSION src_sha256=SOURCE_SHA256
# encoding source=cp932 target=cp932 file=utf-8
# scope kind=all range=ALL part=1/1
# tags name msg choice label ui system ruby misc
#
# idx=00000001 off=0x00000010 tag=msg speaker=NAME
○00000001○msg○こんにちは{{00}}ワールド
●00000001●msg●こんにちは{{00}}ワールド

# idx=00000002 off=0x00000030 tag=msg speaker=NAME
○00000002○msg○さようなら
●00000002●msg●再见
```

刚导出时每块的 `●` 行与 `○` 行完全相同（上面 idx=1 就是未翻译状态，idx=2 是译者已改过的状态）；
块与块之间空一行。


- 文件头四行必填且必须是前四行。`src_sha256` 是**未编辑源工件**的哈希，导入时必须匹配当前
  IR——这是防止用旧文件覆盖新 dump 的唯一有效手段。
- 分片导出时 `part=K/N` 必填；导入必须要求 N 片全到或显式声明部分范围，**不得静默接受缺片**。
- `idx` 三处均为**定宽十进制**。定宽消除分隔符歧义，也让行内正则不需要回溯。
- 分隔符严格成对：原文行三个全是 `○`，译文行三个全是 `●`，**不得混用**。

**元数据行只写导入时真正会校验的字段。** 上面示例给的是字段全集，不是推荐值——实测一份按全集
渲染的译文，70% 的体积是注释，其中仅 `path=` 一项就占 18%。判定标准很简单：

```text
写   idx        三行一致性校验的依据
写   off / inst 检出错位的依据（导入时逐条比对 IR）
写   tag        一致性校验 + 决定 translate_policy
写   speaker    译者判断语气所需，机器不校验但人需要
不写 file       单文件译文里它恒等于文件头的 sample
不写 path       报错信息里的路径应取自 IR，不依赖译文文件
不写 sub/src/refs/pair/kind  除非该项真的会被校验或真的会被译者读
```

逐条自问：**这个字段缺了，是导入会失败，还是只是我少看到一点信息？** 后者一律不写。译文文件
是给人编辑的工作面，不是 IR 的第二份副本——IR 已经有一份了，重复只会让文件更难读、更慢传、更容易
被编辑器改坏。

**同一条标准适用于整行注释，而且更严。** 字段挤在一行里还只是变宽，多余的注释行会把条目块撑开、
打断上下文阅读。判据是：

```text
译者看到这行，能做出什么不同的操作？
  能 → 保留（例如 speaker，影响用词与语气）
  不能 → 删掉，无论它多"有信息量"
```

实测案例：去重条目上方渲染了一行「（同一句还用于 N 处，改这里即全部生效）」。该说明描述的机制
真实且重要，但译者**无法据此采取任何不同操作**（可编辑的只有当前这一条），因此它仅构成每隔数行
出现一次的干扰。共享关系应记入 IR 的 `aliases` 字段供审计，不应出现在编辑工作面。

推论：**机制的重要性不构成在产物中说明它的理由。** 重要机制应写入文档并编码为校验，而不是
在译者每次滚动时重复告知。产物里的每一行都要么被机器校验，要么被人用来做决定。

收窄格式时**必须保留旧格式的读取能力**：正则里把删掉的字段改成可选匹配。已经翻到一半的文件不能
因为格式优化而作废。

```text
^○(?P<idx>\d{8})○(?P<tag>[a-z_]+)○(?P<text>.*)$
^●(?P<idx>\d{8})●(?P<tag>[a-z_]+)●(?P<text>.*)$
```

- **原文行是校验锚，不是装饰。** 导入时逐字符比对 IR 中的 `source`，不一致即拒绝并报出 idx、
  IR 值、文件值。这一条同时捕获错位、误改原文、用旧文件导入、以及编辑器自动替换（全角化、
  智能引号、行尾空格剥离）——比任何行号或计数校验都有效。
- 翻译者**只能改译文行**。

**导出时置 `target = source`，译文行不得留空。** 译者覆盖原文而非填入空白。留空的四项代价：

| 代价 | |
|---|---|
| 无法就地对照 | 译者需回看上一行取原文 |
| 无法判断进度 | 空值既表示未翻译，也可能是误删，二者不可区分 |
| 部分翻译不可回封 | 未编辑条目将以空串写回目标文件 |
| 编辑器中难以阅读 | 连续空白使文件形似损坏 |

「未翻译」的判据因此为 `target == source` 而非空值，报告以此统计（`changed_entries` /
`unchanged`），二者均为合法状态，无需区分未翻译与有意保留原文。

附带效果：以原文回封时输出与原件逐字节相同，故部分翻译在任何阶段均可安全回封并载入运行，未翻译
部分显示原文。留空方案不具备该性质。

推论：预填后**不得**再将空译文行视为合法输入。空的 `●` 行表示内容被误删，须拒绝并报出 idx。

**条目块之间必须有一个空行。** 三行紧邻的块连续排列会导致边界不可辨识。空行不是排版
偏好，它是让人能在几百条里定位一条的最低要求。渲染时每块末尾追加一个空行，解析时忽略空行。

### 4.7 人名绑定

绑定是独立对象（`ir/name_bindings.jsonl`），不是 `TextEntry` 上的一个字段：

```text
NameBinding  binding_id, msg_entry_idx, name_entry_idx, name_kind,
             method, extractor_ids, agreed_by, confidence, candidates, evidence_refs
```

`method` 优先级严格递减，**低优先级不得覆盖高优先级结论**：

| `method` | 依据 | 最高置信度 |
|---|---|---|
| `explicit-id` | 结构中存在显式「名字 ID」字段 | `observed` |
| `slot-ordinal` | 参数块中名字与正文占固定槽位序号 | `derived` |
| `call-structure` | 同一调用点立即数序列中的位置关系 | `derived` |
| `adjacency` | 仅靠条目物理或索引相邻 | `inferred` |

歧义是硬规则。同一 `msg_entry_idx` 有多个名字候选、或多个提取器结论不同时：`confidence=
ambiguous`、`candidates` 保留全部候选及证据、严格模式**拒绝**输出确定值、双行文件的 `pair=`
写 `AMBIGUOUS` 并在注释中列候选 idx。

**禁止「第一个匹配的是名字」「最后一个立即数是正文」这类顺序偏好。** 参数顺序变化时这会系统性
把名字和正文对调，而两者都是合法文本，任何长度或编码检查都不报错——错误只会在游戏里显示为
张冠李戴。

`name_kind=virtual` 用于名字不作为独立文本条目存在（写死在代码里、或由 ID 映射到名字表）。
虚拟名须记来源与解析方式；若不可回封则 `frozen`，**不得**伪造成可编辑的 `name` 条目。

### 4.8 派生标注层

有些角色只能靠上下文段落推出，而非单条锚点。例如：被场景边界包围的连续条目中，夹在两条 `msg`
之间且形态像人名的短条目。这类推导允许存在，但必须隔离：写 `derived_tag` /
`derived_tag_source=contextual`，**不覆盖** `tag`；导出时若使用它，注释行必须同时给 `tag=` 与
`derived=` 让审阅者看见不一致，该选择记在文件头；派生标注不得进重定位图、不得改变 `frozen`、
不得作为提级 tier 的证据。

### 4.9 导入校验清单

按序全过才生成 Patched IR，任一失败即拒绝整个文件：

```text
1  src_sha256 与当前 IR 匹配        8  frozen 条目的译文行未被改动
2  IR / 工具版本兼容                9  target_encoding 可表示（无静默替换）
3  分片完整（全到或显式范围）       10  字节长度符合回封模式
4  idx 定宽、唯一、存在于该源      11  终止符与占位符集合完整（ph_hash 一致）
5  三行 idx 一致、tag 一致          12  pair 引用存在且未指向错值
6  分隔符未混用                    13  译文行非空（空 = 误删，不是"未翻译"，§4.6）
7  原文行与 IR 的 source 逐字符相等
```

第 13 条的存在依赖导出时预填原文：既然每条一开始就有内容，空行只可能是误删，必须报错并指出 idx。
把它当作"未翻译"会让误删静默变成把空串写回目标文件。

第 4 条的「该源」不可省略：合库布局下 `idx` 只在 `src_id` 内唯一（§2.3），必须先用文件头的
`src_sha256` 经 `manifest.jsonl` 定位到源，再在该源的条目集合内校验唯一性与存在性。跨源合并成
一张平表会让不同源的同号条目互相覆盖，且第 1 条的哈希校验会退化为「只对第一个源成立」。

---

## 5. asm.txt：语义化视图与结构编辑面

从 IR 投影生成。它既是审计视图，也是**结构编辑面**（§2.5）——因此格式必须稳定且可 diff。

- 纯文本，每行一条记录。**绝不出现原始十六进制转储。**
- 注释只允许 `;` 开头的**语义**注释。**绝对禁止**在注释里写原始字节序列（如 `; 00 01 FF`）。
- 标签定义前**必须插入一个空行**（文件首个标签可例外），格式 `label_name:`，不缩进。
- 指令引用**标签**，不引用硬编码偏移。
- 字符串用 `.string "..."`，内容按选定编码可读，特殊字节用占位符（§4.5）。其他数据用
  `.byte`/`.word`，十进制或 `0x` 列出；这些定义中不得夹杂原始字节注释。
- **地址空间全覆盖**：指令流之外的数据块（字符串表、指针表、对齐填充、未知区）也必须以伪指令
  完整呈现，确保汇编器能重建所有字节。T1/T2 区域用 cell 伪指令表示，不伪装成指令。

作为编辑面的三项附加要求：

- **渲染确定性**：见 §2.6——diff 机制的前提，须以测试锁定。
- **每行带定位信息**：行首的偏移是改动映射回 IR 对象的依据。缺它则 diff 出的改动无法定位。
- **字符串行显式带 `sid`**：共享节点在 asm 中被压缩为 `-> @0xXXXX (共享)` 引用标记，无 `sid` 时
  无法从 asm 侧判断两行是否共用一份存储。加上后人读 asm 也能直接看出共享关系。

不可编辑的部分必须显式标注。以下三类被改动时须拒绝而非尝试重建（均为实测遇到的格式性质）：

```text
存储宽度非最小宽度   表中所存整数宽度必须原样重放，重算会破坏逐字节一致
名称树含不可达槽位   重新生成的树不会与原字节相同
共享子树             改一处等于改全部引用点，不存在"只改一处"的语义
```

```asm
; 脚本入口
.encoding "cp932"
.dialect  "ENGINE_ID" version "1.0.0"
.tier     "T2"

loc_00000000:
    LOAD    R1, 0x1234
    CALL.PRINT_TEXT    loc_00001000        ; 引用 idx=00000001，站点 join_id=J0001

loc_00001000:
    .string sid=1131 "こんにちは{{00}}ワールド"    ; idx=00000001

loc_00001008:
    .ref    sid=1131                       ; 共享同一存储，改上面那条即全部生效

loc_00001010:
    .byte 0x01, 0x02
```

---

## 6. 回封策略：由 tier 决定，不是用户偏好

| 策略 | 最低 tier | 允许的变化 | 必须已解析 |
|---|---|---|---|
| `identity` | T1 | 无（零编辑往返） | cell 切分或 opaque 边界 |
| `in_place` | T2 | 编辑后字节数 ≤ 原槽容量 | 每个文本槽的起止与容量 |
| `pointer-rewrite` | T2 | 文本任意变长，引用槽原地回填 | 全部引用站点集合 |
| `full-layout` | T3 | 结构重排、条目增删、跨层尺寸变化 | 全部指针/跳转/表容量/校验依赖 |

`identity` 是其余策略的前置：**未通过零编辑往返，禁止进入任何编辑流程。**

改动来自哪个编辑面（§2.5）决定所需策略：

| 改动来源 | 所需策略 | 所需 tier |
|---|---|---|
| `texts/` 的 `●` 行，编码后未超容量 | `in_place` | T2 |
| `texts/` 的 `●` 行，编码后超出容量 | `pointer-rewrite` | T2 |
| `asm.txt` 的字符串行（`.string`） | 等同文本改动，按上两行处理 | T2 |
| `asm.txt` 的指令、数据或结构 | `full-layout` | **T3** |
| 两个编辑面均无改动 | `identity` | T1 |

**改 asm 结构需 T3**，因为要重算跳转目标与表容量；改字符串只需 T2，因为只需回填引用槽。工具按
文件哈希判定 `asm.txt` 是否被改动，改动了结构而 tier 不足时**明确拒绝并说明缺哪类证据**，而不是
尝试后失败（§6.1 的 `TIER_TOO_LOW`）。

### 6.0 三条不可混淆的语义

```text
零编辑回封  未修改任何条目            输出与原件逐字节相同，三种哈希相同
等长回封    已修改但编码后未超容量    哈希必然改变，总长度不变
变长回封    修改后超出原容量          总长度改变，全部引用需重新计算
```

**「原地回封保持哈希一致」仅在零编辑时成立。** 译文与原文不同时输出哈希**必须**改变——哈希未变
即表示编辑未生效。报告须区分两个结论，不得合并为「哈希一致」：

| 场景 | 期望 | 哈希不符时 |
|---|---|---|
| 零编辑 | 与原件逐字节相同 | **失败**：解析或重序列化存在缺陷 |
| 有编辑 | 与原件不同，每处差异可追溯到具体条目 | **失败**：编辑未生效或写入位置错误 |

`identity` 验证前者，`in_place` 与 `pointer-rewrite` 验证后者。以「与原件哈希相同」作为编辑后的
成功条件，会把「编辑被静默丢弃」判为通过。门禁：`scripts/check_determinism.py edit`（§8.2）。

### 6.0.1 文本变长必须支持，且为主要用例

本地化的常态是译文长度超过原文（日译中通常偏短，日译英显著偏长）。因此：

- **`in_place` 不得作为唯一实现**：仅支持等长回写的工具在真实任务中不可用——译者首次遇超长即被
  阻断，且无法通过改写措辞规避（专有名词、数字、标点均可能致长度上升）。
- **超长不是错误，而是切换策略的信号**：应报告「需改用 `pointer-rewrite`」并给出超出字节数，
  不得要求译者压缩文本以适配容量。
- **`pointer-rewrite` 为默认变长路径**，前提是引用站点集合完整（§3、§6.3）。

### 6.0.2 长度计算的唯一口径

超长判定依赖精确字节数。以下任一项遗漏都会产生偏差：本可回封的内容被拒绝，或超长未被检出而
写坏文件。

```text
encoded_len(text) =
      len(非占位符片段按 target_encoding 编码后的字节)
    + sum(各占位符展开后的原始字节数)      # {{0A}} 计 1 字节，而非 6 个字符
    + terminator_len                       # NUL 结尾格式计 1，长度前缀格式计 0
```

配套规则：

- **按 `target_encoding` 计算，不按字符数。** 同一段中文在 UTF-8 下约为 GBK 的 1.5 倍；按字符数
  判定会在两种编码下得出不同结论。
- **占位符按展开后的字节计**（§4.5）。`{{0A}}` 在译文文件中占 6 个字符，在目标文件中占 1 字节。
- **终止符计入容量。** 以 NUL 结尾的字符串，容量为「原始字节数 + 1」；漏算会使恰好等长的译文
  覆盖终止符，导致越界读取。
- **容量来源必须显式记录**，不得由相邻条目偏移相减隐式推断：

```text
slot_capacity 的合法来源
  显式长度字段       容器中存有该条目长度 → 直接采用
  终止符扫描         自起始偏移扫描至终止符 → 容量为差值
  下一条目起始偏移   仅当已证明条目**紧密排列且无 padding** 时可用
```

第三种来源最易出错：条目间若存在对齐 padding，相减所得容量偏大，据此判定为「未超长」的译文会
覆盖 padding 乃至下一条目的头部。未证明紧密排列时该来源视为不可用，`in_place` 的 probe 返回
`CAPACITY_UNKNOWN`（§6.1）。

### 6.0.3 变长回封的完整传播

文本长度变化后必须按序处理下列各项，缺任一项都会产出可加载但错位的文件：

```text
1  按 target_encoding 重新编码，占位符展开为原始字节
2  重排数据区，按格式声明的对齐重新计算各条目的新起始偏移
3  按 JoinSite 集合回填全部引用（§6.3：按站点，不按值）
4  更新容器中的长度、计数与偏移表字段
5  重算受影响的校验和（内层先于外层）
6  按 layer_stack 逆序恢复封装层
7  重新解析输出，验证站点集合同构（§6.3）
```

第 2 步的对齐使用 `aligned = ceil(offset / N) * N`，N 取自格式模型，**不得沿用旧偏移**。
第 5 步的顺序不可颠倒：外层校验和覆盖内层数据，先算外层将得到基于旧内容的值。

变长后**必须重新验证的性质**（与零编辑的验证项不同）：

```text
□ 输出可被自身完整重新解析（不限于检查魔数）
□ 重新解析后 byte_coverage 仍为 1.0，无缺口、无重叠
□ 校验和字段自洽（重算值等于写入值）
□ 站点集合与原集合同构：数量相同，site_offset 一一对应
□ 每处已编辑条目的新内容确实出现在输出中
□ 未编辑条目的字节内容逐条不变
□ 总长度差值等于各条目长度变化之和加对齐调整量（差值可解释，无意外增减）
```

倒数第三项不可省略：「文件可解析」不能证明「译文已写入」，必须反查输出中确实包含新文本。

### 6.1 probe / run 协议

```python
class RepackStrategy(Protocol):
    strategy_id: str
    required_tier: str
    def probe(self, ir, options) -> ProbeVerdict: ...   # 只读、无副作用
    def run(self, ir, options) -> RepackReport: ...
```

```text
ProbeVerdict  applicable, reason_code, reason_detail, blocking_refs, estimated_deltas
reason_code ∈ {OK, TIER_TOO_LOW, LENGTH_OVERFLOW, UNRESOLVED_JOIN_SITE, AMBIGUOUS_JOIN_KEY,
               ENCODING_UNREPRESENTABLE, PLACEHOLDER_BROKEN, UNREPLAYABLE_TRANSFORM,
               CHECKSUM_DEPENDENCY_UNKNOWN, CAPACITY_UNKNOWN}
```

`probe` 必须只读无副作用——这是它能被安全地对全部策略批量调用的前提。

### 6.2 auto 是能力协商，不是「试到不报错」

1. 对全部策略调用 `probe` 收集裁决。**此阶段不执行任何 `run`。**
2. `applicable=false` 的 `reason_code` 与 `blocking_refs` 进报告。
3. 在可用策略中选**能力最小**的：`identity` < `in_place` < `pointer-rewrite` < `full-layout`。
   能不改引用就不改，能不重排就不重排。
4. 执行选中策略的 `run`。
5. **`run` 失败不自动降级到下一策略。** 写 checkpoint、报出全部裁决、停止。

第 5 条是纠错规则。「probe 通过但 run 失败」意味着 probe 的判据与实际约束不一致——这是 probe 的
缺陷，必须修 probe，而不是靠回退掩盖。自动回退会让本该被发现的缺陷永久隐藏，并让用户拿到一个
由未预期策略生成的文件却以为用的是选中策略。失败后唯一允许的自动行为：清理未提交临时输出，
保留事件日志与 checkpoint。

报告必须列出**全部**策略的裁决，不只是选中的那个：

```json
{"selected_strategy": "pointer-rewrite",
 "selection_rule": "minimum-capability-among-applicable",
 "verdicts": [
   {"strategy_id": "identity",        "applicable": false, "reason_code": "LENGTH_OVERFLOW",
    "blocking_refs": ["idx=00001204"]},
   {"strategy_id": "in_place",        "applicable": false, "reason_code": "LENGTH_OVERFLOW",
    "blocking_refs": ["idx=00001204", "idx=00001987"]},
   {"strategy_id": "pointer-rewrite", "applicable": true,  "reason_code": "OK",
    "estimated_deltas": {"ranges": 2, "bytes": 46}},
   {"strategy_id": "full-layout",     "applicable": false, "reason_code": "TIER_TOO_LOW",
    "blocking_refs": ["R_SCRIPT_MAIN"]}]}
```

用户可显式指定策略越过最小能力原则，但不得越过 `required_tier` 与 `applicable=false`。显式
指定一个不适用的策略是错误，不是覆盖。

### 6.3 变长回封：按站点，不按值

本规范最重要的纠错规则。

```python
# 正确
for site in join_sites:
    write_u32(out, site.site_offset, new_offset[site.key_value])

# 错误
for word in all_words:
    if word.value in old_to_new:
        word.value = old_to_new[word.value]
```

值匹配会命中所有**恰好等于任一旧偏移**的字——常量、坐标、标志位、时间参数、另一张表的容量——
把它们静默改成新偏移，产出一个能加载但行为错乱的文件。这类损坏**不会被哈希检出**（编辑版本
就该变），**也不会被区间覆盖检出**（长度没变）。唯一能挡住它的是站点级溯源：

- 每个被改写的字节范围必须能追溯到一个 `join_id`，写入 `relocation_log.jsonl`。
- 站点集合外的位置一律 `preserve`，即使其值等于任一旧键。
- **站点同构验证**：回封后重新解析，比较新旧站点集合——数量相同、`site_offset` 逐一对应、
  `key_kind` 相同、`key_value` 按映射变化。任一站点消失或新增即拒绝输出并保留失败样本。

`preserved_value_collisions`（值等于某旧键但因不在站点集合中而被保留的位置数）是关键诊断量：
不为零是正常的，**为零反而值得怀疑键域是否过窄**。

### 6.4 布局与传播

任何编辑先生成不可变 `ChangeSet`，再算影响闭包。文本长度变化的传播链：

```text
TextEntry → 编码后字节 / 终止符 / 占位符 → JoinSite 集合（按站点回填）
  → Instruction size / label / 跳转目标 / VM 校验      仅 T3+
  → payload 大小 / 层内偏移 → 压缩或加密层
  → VfsEntry 存储大小 / stored_block_sha256
  → FAT / 后续条目 offset / 归档校验 → 外层 transform / 全局签名字段
```

只按**叶到根**顺序重序列化：先验 IR，再验子工件，再更新父条目，最后重建外层。影响闭包中存在
未解析指针、跳转、FAT 引用、校验依赖或不可重放 transform 时阻断 `full-layout`。这样才能防住
「脚本正确但外层归档错位」和「归档能开但 VM 跳转已失效」这两种局部成功。

布局求解器先算全部存储尺寸，再按原始顺序求解 offset、对齐、padding、表容量、指针宽度、压缩
边界、校验顺序；重复「放置 → 回填引用 → 写校验 → 更新依赖尺寸」直到稳定。对齐用
`aligned = ceil(offset / N) * N`，N 由格式模型提供，**不硬编码旧偏移**。未修改块按
`stored_block_sha256` 或 `raw_identity` 复用，只有变更块重新编码。

### 6.5 事务与产物

```text
写 tmp/ → flush+fsync → 重新解析并执行该策略要求的全部验证 → 原子改名到 rebuilt/
```

验证失败的产物留在 `tmp/failed/` 供诊断，不进 `rebuilt/`。

**明文产物与加密/封装产物必须共存且分开命名。** 用加密结果覆盖同名明文产物会让「重新解析验证」
失去对照物，也让用户无法判断拿到的是哪一版。按层栈逆序恢复封装后，两者各自独立落盘，报告中给出
各自哈希与层栈。

---

## 7. opcodelist.py：声明式方言，不是代码堆

引擎适配器天然含两类内容：**结构逻辑**（cell 切分、锚点匹配、容器头解析、引用槽回填——跨引擎
共享的算法）和**方言数据**（opcode 数值、调用 ID、字段偏移、编码、文本分类规则——逐引擎不同）。

混在同一个类里会产出几百行的文件：正则常量、硬编码十六进制集合、`_looks_like_*` 判定方法穿插在
真正的解析逻辑之间。后果不是「代码丑」，而是三个可验证性损失：方言值无法被证据追溯（无法判断一个
ID 是从宿主反汇编推出的还是从命中率猜的）；分类规则无法被单独测试和统计；方言不可移植（同引擎
另一个游戏 opcode 略有偏移就只能复制整个类）。

```text
core        与引擎无关：区域、cell 切分、引用连接、布局求解、证书、事务
opcodelist  声明式数据：无控制流，可序列化，可 diff，可校验
profile     结构逻辑：读取方言，实现算法，不含引擎特定字面量
```

**硬规则：结构逻辑代码中不得出现引擎特定的魔数、opcode 值、调用 ID 或文本正则。** 这条可机械
检查——在 profile 模块中搜索十六进制字面量与正则字符串，命中即违规。

```python
DIALECT = {
    "schema_version": "1.0.0", "engine_id": "ENGINE_ID", "endianness": "little",

    # cells.evidence 即 §1.2 申报 T1 所需的两条独立证据
    "cells": {"size": 4, "alignment": 4,
              "evidence": ["file-size-divisible", "anchor-values-aligned"]},

    "anchors": [
        {"id": "call", "kind": "call",
         "pattern": "OPCODE_HEX 00000000", "mask": "FFFFFFFF 00000000",
         "operand_slots": [{"ordinal": 1, "name": "callee_id", "width": 4}],
         "evidence_refs": ["EV_CALL_DISPATCH"], "confidence": "derived"}],
        # param-set 形态另加 slot_selector{field_mask,field_value,ordinal_mask} 与 stride

    "callee_groups": [
        {"id": "message", "ids": ["CALLEE_HEX"], "role": "msg",
         "evidence_refs": ["EV_MSG_RENDER"], "confidence": "derived"},
        # 成对结构用 open_id/close_id 加 terminator:"structural"，优于固定窗口
    ],

    "windows": [
        {"name": "param_lookahead", "value": 16, "measured_max": 11,
         "evidence": "样本 SAMPLE 实测最大跨度 11 字", "on_exceed": "blocked"}],

    "container": {
        "header": {"size": 16,
                   "fields": [{"name": "entry_count", "offset": 12, "width": 4, "kind": "u32"}]},
        "entry":  {"id_width": 4, "terminator": "00"},
        "cipher": {"algorithm": "ALGORITHM_ID",
                   "applies_when": {"offset": 0, "equals": "MAGIC_HEX"},
                   "params": {}, "evidence_refs": ["EV_CIPHER"]}},

    "opcodes": {
        0x10: {"mnemonic": "CALL", "length": 5,
               "operands": [{"type": "sub_opcode", "bits": 8},
                            {"type": "rel_offset", "bits": 32, "base": "instruction_end"}],
               "sub_opcodes": {0x00: "PRINT_TEXT", 0x01: "PLAY_SOUND"},
               "evidence_refs": ["EV_CALL_TABLE"], "confidence": "derived"}},

    "text_rules": [
        {"id": "font-family", "subtype": "font-family-name",
         "requires_callee_group": "font",     # 前置：已由锚点证明为文本参数
         "predicates": [{"kind": "max_length", "value": 12},
                        {"kind": "contains_script", "value": "cjk-or-kana"}],
         "tag": "misc", "tag_source": "heuristic", "confidence": "inferred"}],
}
```

每个 `anchors`/`callee_groups`/`opcodes` 条目必须带 `evidence_refs` 与 `confidence`。
`confidence=inferred` 的组只能产出 `tag_source=heuristic` 的标注，不能作为 `derived`。

**谓词是闭集**，由 core 实现，方言只组合不新增：`max_length`、`min_length`、
`contains_script`、`any_char_in`、`all_chars_in`、`matches_regex`、`ascii_ratio_gte`、
`has_digit`、`starts_with`、`ends_with`、`requires_callee_group`、`requires_anchor_kind`。

`matches_regex` 存在但受限：正则写在方言声明里而非代码里，因此可被审阅、统计、单独测试。规则
命中数**必须逐规则统计**写入 `rule_hits.json`——一条规则命中零次或命中过多都是需要复查的信号。
规则按声明顺序求值，首个命中即返回并记 `matched_rule_id`。**没有兜底规则**（§4.3）。

**`vm_analysis.md` 是证据台账**，逐项记录每个方言数值的来源。这不是文档义务，是提级依据——
§1.2 要求的两条独立证据就登记在这里：

```markdown
### EV_MSG_RENDER — 消息显示调用 CALLEE_HEX
- 证据等级：derived
- 来源：宿主 HOST_BINARY 偏移 0x4A120 的调用分发表第 N 项，跳转至文本渲染函数
- 交叉验证：样本 SAMPLE 中该 ID 的 1,284 个锚点命中全部带 2 个文本参数槽
- 反例检查：该 ID 未出现在不含文本的脚本区
- 未决：ID 高 16 位含义未确认
```

同引擎的不同游戏共享结构逻辑，各自一份方言声明，用 `schema_version` 与证据台账区分。新游戏的
适配成本降为「写一份方言 + 记录证据」，而不是复制一个几百行的类。

### 7.1 同引擎多版本：差异分级与形态派发

上一节假设「一个方言对应一部作品」。真实情况更复杂：同一引擎跨数年演进，不同作品之间既有完全
一致的部分，也有结构性不兼容的部分。本节规定如何在**一套代码**内兼容。

#### 7.1.1 先分级，再选兼容机制

按**差异所在层级**分三级，每级只用对应机制：

| 级别 | 差异内容 | 兼容机制 | 判定方法 |
|---|---|---|---|
| **L1 参数级** | 同结构，数值不同：opcode、调用 ID、字段偏移、编码、窗口常量 | 换方言声明，代码零改动 | 形态签名相同，仅字面量不同 |
| **L2 形态级** | 同语义，结构不同：平铺 ↔ 嵌套、槽位数 5/6/9、字段顺序 | 同一提取器内多形态派发（§7.1.3） | 形态签名不同，目标语义一致 |
| **L3 代级** | 语义模型不同：容器格式、类型系统、封装层 | 独立 profile，共享 core | 容器头字段或类型编码不兼容 |

误判级别的代价是确定的：**L2 当 L1**（只改数值）→ 提取结果为空；**L2 当 L3**（复制 profile）→
两份近似代码需同步维护，修一处 bug 要改两遍。

实测案例属 L2：同引擎两部作品的 `texts[]` 一为 6/9 槽平铺、一为 5 槽且正文嵌在语言列表内，按 L1
处理时提取出 0 条正文。

#### 7.1.2 版本识别必须基于结构证据

**禁止依据文件名、扩展名、目录名或作品名选择方言。** `.txt.scn` 与 `.ks.scn` 的扩展名差异与内部
结构无必然关联，同一作品内也可能混用多种形态。

识别顺序：

```text
1  容器级：签名、版本号、头长度、字段布局   → 决定 L3（选哪个 profile）
2  方言级：锚点命中率、调用 ID 集合交集     → 决定 L1（选哪份方言声明）
3  形态级：逐条目统计形态签名               → 决定 L2（每个条目走哪个分支）
```

第 3 步的粒度是**条目**而非文件：同一文件内不同条目可能形态不同，必须逐条判定。以文件为单位
选定形态，会让少数异形条目被静默跳过。

方言选择的结果与证据必须写入 `case.json` 与报告：

```json
{
  "profile_id": "PROFILE_ID",
  "dialect_id": "DIALECT_ID",
  "dialect_selection": {
    "method": "structural-probe",
    "evidence": ["signature=PSB\\0", "version=3", "header_len=0x2C"],
    "candidates_rejected": [{"dialect_id": "OTHER", "reason": "锚点命中率 0.3%"}]
  },
  "shape_signatures": {"5-slot-nested": 607, "9-slot-flat": 0}
}
```

`candidates_rejected` 不可省略：它是"为何不是另一个方言"的证据，也是方言选错时的第一手线索。

#### 7.1.3 形态派发：并列分支，禁止回落

L2 的实现形态固定为**并列判定 + 显式兜底失败**，而不是「先试已知的，不行就算了」：

```python
def extract_entry(doc, entry_off, dialect):
    """按形态派发。每个分支自带判定条件，判定失败不回落到其他分支。"""
    for shape in dialect.entry_shapes:          # 声明顺序即判定顺序
        if shape.matches(doc, entry_off):       # 纯谓词，不产生副作用
            return shape.extract(doc, entry_off)
    # 没有任何形态命中：记为未解析，而不是返回空结果
    raise UnknownEntryShape(offset=entry_off,
                            signature=shape_signature(doc, entry_off))
```

四条硬规则：

- **`matches` 必须是纯谓词**，判定与提取分离，报告方能给出命中了哪个形态。
- **无形态命中时必须失败**，不得返回空列表——返回空正是 §0 那次事故的直接成因：平铺分支「成功」
  匹配了一个全为 `null` 的结构。
- **形态间不得共享可变状态**：新增形态不得改变既有形态的行为，这是 §0.3「旧样本产出条数完全不变」
  可回归的前提。
- **未命中的形态签名进入报告**，与 `unresolved` 一同统计——签名分布是发现新变体的唯一线索。

形态在方言中声明，判定条件与提取路径都是数据：

```text
"entry_shapes": [
    {"id": "9-slot-flat",
     "match": {"slot_count": 9, "slot_types": {2: "string"}},
     "text_slots": {0: "name", 2: "msg", 7: "msg", 8: "msg"},
     "evidence_refs": ["EV_SHAPE_9SLOT"]},
    {"id": "5-slot-nested",
     "match": {"slot_count": 5, "slot_types": {1: "collection"},
               "nested": {"host_slot": 1, "language_index": 0}},
     "text_slots": {0: "name"},
     "nested_text_slots": {0: "name", 1: "msg", 3: "msg", 4: "msg"},
     "evidence_refs": ["EV_SHAPE_5SLOT_LANG"]},
]
```

如此新增一个变体的成本是**追加一条声明加一份证据**，而不是改动结构逻辑。若某变体的判定或提取
确实无法用现有谓词表达，才扩展 core 的谓词集合——扩展后所有方言都能使用，仍不产生引擎特定代码。

#### 7.1.4 共享与分叉的判据

面对新版本时，是复用现有 profile 还是新建，用下表判定，避免凭直觉决定：

```text
容器头、类型系统、封装层  完全兼容  → 同一 profile，新增方言或形态声明
容器兼容、语义模型不同              → 同一 profile，新增形态声明（多数情况在此）
容器头字段布局不兼容                → 新 profile，共享 core
值类型编码方式不兼容                → 新 profile，共享 core
```

**分叉的代价必须显式承认**：新建 profile 意味着此后每个跨版本 bug 都要修两处。因此只在容器级
不兼容时才分叉；语义层差异一律用形态声明解决。

反向约束同样成立：**不得为了"共享代码"把不兼容的容器格式硬塞进同一个 profile**。判据是
§7 的硬规则——若共享导致结构逻辑里出现 `if version == X` 之类的引擎特定分支，说明该分叉。

#### 7.1.5 跨版本回归是硬要求

新增方言或形态后必须验证既有版本未受影响：

```text
□ 全部既有样本的产出条数**完全不变**（实测为 66,334 条前后一致）
□ 全部既有样本的零编辑往返仍逐字节一致
□ 新样本的 ASM 与 IR 哈希可复现（同一输入两次运行结果相同）
□ 新旧样本的形态签名分布均记入报告，可对比
□ 新增形态的分支被实际命中（覆盖率非零，否则声明形同虚设）
```

最后一条防止一类隐蔽失败：新增了形态声明，但判定条件写错导致从未命中，而既有分支恰好"成功"
返回空结果——此时全部门禁通过，提取结果依然是错的。

---

## 8. 覆盖证书

```json
{"schema_version": "1.1.0", "layer_id": "L000", "source_size": 0,
 "intervals": [], "gaps": [], "overlaps": [], "status_counts": {},
 "byte_coverage": 1.0, "structural_coverage": 1.0,
 "tier_coverage": {"T0": 0, "T1": 0, "T2": 0, "T3": 0, "T4": 0},
 "min_tier": "T1", "declared_capabilities": ["roundtrip", "in_place"],
 "tier_blocked": [], "instruction_coverage": "not_applicable",
 "tag_source_counts": {"structural": 0, "anchor": 0, "binding": 0,
                       "heuristic": 0, "user": 0, "unresolved": 0},
 "transform_edges": [], "roundtrip": {}, "toolchain": {}}
```

每个 `intervals[]` 项：`id, layer_id, start, end, status, kind, raw_sha256, owner,
decode_tier, tier_evidence_refs, tier_blocked_at, confidence, evidence_refs, rewrite_policy`。
T1 另存 `cell_size/cell_count/endianness`；T2 另存
`anchor_ids/anchor_hit_count/join_site_count`；T3+ 另存 `opcode/variant/operands/label/target`。

| 状态 | 含义 | 回封策略 |
|---|---|---|
| `decoded` | 格式、指令或字段由证据确认 | 可从 IR 编码 |
| `structured-unknown` | 边界/字段稳定，语义未定 | 默认原样保留 |
| `unknown_opaque_block` | VM/封装未知字节 | 逐字节复制 |
| `opaque-preserved` | 非关键但未解释的容器/元数据 | 逐字节复制，记回封位置 |
| `padding` | 对齐或格式允许的填充 | 仅按规则生成 |
| `proven-gap` | 缺失或无法观测 | **阻断严格成功** |

未知 opcode 用 `unknown_opaque_block` 保留，**不得用 opaque 掩盖已知代码的解码失败**。

### 8.1 严格成功的充要条件

```text
□ 区间恰好覆盖 [0, source_size)，首段从 0 起、末段止于 N
□ 无 gap / overlap / proven-gap
□ 每段 raw_sha256 可从源按范围流式复算
□ tier_coverage 各值之和 == source_size；min_tier 与区间中的最低 tier 一致
□ declared_capabilities ⊆ min_tier 允许集合（§1.3）
□ instruction_coverage 仅在 min_tier>=T3 时为数值且须为 1.0，否则 not_applicable
□ byte_coverage == structural_coverage == 1.0（与 tier 无关）
□ tier_coverage["T3"] > 0 时对应区间必须提供长度算法与 operand_schema
  （专门检出「把 cell 伪装成指令」）
□ 全部 transform 输入/输出哈希可复核，按父到子拓扑验证、回封按逆序重放
□ 未编辑样本逐字节一致（三种哈希）
□ 编辑版每个差异范围都对应 IR 编辑或声明的校验重生成，且能追到 join_id / region_id
□ 站点集合回封前后同构（§6.3）
□ 同一输入跑两次，报告与 IR 的规范化哈希相同
```

`tier_blocked` 不为空**不影响**严格成功——回落并如实申报是合法结论。

### 8.2 可执行门禁

规则能机械检查的就不要只写在文档里。本技能自带七个门禁脚本，交付前须全部通过（退出码 0）：

```console
python scripts/check_output_sanity.py reports/extract_report.json
python scripts/check_shapes.py        reports/shapes.json --corpus-wide \
                                      --baseline reports/shapes_baseline.json
python scripts/check_determinism.py   rerun asm/A.asm.txt asm/A.asm.run2.txt
python scripts/check_determinism.py   edit SAMPLE rebuilt/SAMPLE --no-edit
python scripts/coverage_certificate.py SAMPLE reports/coverage_certificate.json
python scripts/check_dsat.py          ir/ texts/
python scripts/check_sites.py         SAMPLE rebuilt/SAMPLE ir/join_sites.jsonl \
                                      --relocation-log reports/relocation_log.jsonl
python scripts/check_no_literals.py   SRC_DIR --exclude opcodelist
```

| 脚本 | 守住的规则 | 拒绝的情形 |
|---|---|---|
| `check_output_sanity.py` | §0.1 产出合理性 | 必需类别为 0、单一类别占比 >95%、抽出条数与容器对象数量级不符、跨样本密度差一个数量级 |
| `check_shapes.py` | §0.2 / §7.1.5 形态穷举 | 观测到未声明的形态、声明的形态从未命中、形态匹配了条目却产出 0 条文本、形态分布相对基线漂移 |
| `check_determinism.py` | §2.6 渲染确定性、§6.0 哈希语义 | 两次运行产物不同、零编辑却哈希改变、**有编辑却哈希未变** |
| `coverage_certificate.py` | §8 区间、哈希、gap/overlap | 缺口、重叠、哈希不符、覆盖率不足 |
| `check_dsat.py` | §4.6 / §4.9 全部 13 条 | 改原文行、改 idx/tag、idx 非定宽、混用 `○●`、删行、译文行空、整块交换、换文件头哈希、缺分片、改 `frozen`、占位符破损或小写、译文超长、目标编码不可表示 |
| `check_sites.py` | §6.3 按站点不按值 | 值碰撞常量被改写（等长与变长两种输出均检查）、站点集合不同构、差异范围无法追溯到 `join_id` |
| `check_no_literals.py` | §7 方言与代码分层 | 结构逻辑里出现十六进制魔数、字节串签名、opcode/ID 表、内联正则 |

**四条最易漏的检查**，共同点是均不会被哈希或区间覆盖发现：

| 检查 | 捕获的失败 |
|---|---|
| `REQUIRED_TAG_ZERO` | 全部字节门禁通过，却一条正文都没提取到（§0） |
| `BARREN_SHAPE` | 形态匹配成功但产出为空——分支「成功」匹配了全为 `null` 的结构 |
| `EDIT_LOST` | 编辑后哈希未变，即编辑被静默丢弃；把「哈希相同」当成功条件正会放过它 |
| `VALUE_MATCH_REWRITE` | 按值匹配改写引用，产出能加载但行为错乱的文件（§6.3） |

两个脚本区分失败与提示，避免判据不可靠时误杀：

- `check_no_literals.py`：十六进制魔数、ID 表、内联正则为 `violations`（失败）；十进制字面量为
  `advisory`（需人工判断是否为未申报的窗口常量，§1.6）。确属通用常量时在该行加注释
  `dialect-literal-ok` 豁免并写明理由。
- `check_shapes.py`：「声明的形态从未命中」仅在 `--corpus-wide` 下判定失败——单个文件只呈现部分
  形态属正常，逐文件判定会产生大量假阳性。

两处与合库布局（§2.3）相关的接口约定：

- `check_dsat.py` 按 `src_id` 分组读 `text_entries.jsonl`，并用各译文文件头的 `src_sha256` 到
  `manifest.jsonl` 反查它属于哪个源。**多源时 `manifest.jsonl` 必需**——`idx` 只在源内唯一，把
  合库读成一张平表会让不同源的同号条目互相覆盖。分片完整性也按源统计。
- `check_sites.py` 的值碰撞检查在变长输出下改用**计数法**（比较某旧键在站点集合外的出现次数），
  等长输出下用偏移法（可报出精确偏移）。变长时差异范围归属检查默认跳过并在报告中记
  `diff_attribution=skipped-length-changed`，因为插入会使其后每个字节都不同；需强制检查时加
  `--strict-diff`。

七个脚本均只读输入、以 JSON 报告结果、退出码 0/1，可直接接入 CI 或 `pytest`。**不得为了通过门禁
放宽脚本判据**——门禁失败说明实现有问题，或该规则确实需要修订（那要连同 SKILL.md 一起改）。

### 8.3 门禁本身必须先被校准

上一条的前提是门禁报告的问题真实存在。该前提**不会自动成立**。

实测案例：`check_no_literals.py` 首次运行于一份分层良好的实现时报出 7 处违规，逐条核对后确认
全部为假阳性——`str.split(":")` 被识别为 `re.split`，解析**自有产物格式**的正则被要求移入 dialect。
修正判据后同一份代码报 0 处违规，而确实存在混层的对照实现仍报 96 处。

假阳性的危害大于漏报：它会使使用者习惯性忽略门禁输出。因此每个门禁投入使用前必须双向校准：

```text
□ 阳性对照：对**已知违规**的输入运行，必须报出（对照实现报 96 处）
□ 阴性对照：对**已知合规**的输入运行，必须无报告（受测实现报 0 处）
□ 逐条核对每一处报告，确认指向真实问题而非判据缺陷
□ 无法自动判定的类别降级为 advisory，不得据此判定失败
□ 双向用例：判定方向相反的两条规则各测两次
  （零编辑须哈希相同、有编辑须哈希不同——两者互为对照，缺一即无法发现方向写反）
   （十进制字面量属于此类：500 可能是未申报的窗口常量，80 只是预览长度）
```

第四条为通用原则：**判据不可靠时报告但不阻断**，避免在误判与放行之间二选一。

本技能自带的七个门禁均按此校准过。以 `check_output_sanity.py` 为例：阳性对照取实测那次事故的
产出（418 条中 msg 为 0），三条判据独立命中；阴性对照取修复后的产出（1,271 条含 838 msg）与既有
语料的三个正常样本，均无报告。`check_determinism.py` 的六个用例覆盖判定方向相反的两组，确保
「有编辑却哈希未变」不会被当作成功。

**漏报同样只能靠阳性对照发现，且比假阳性更难察觉。** 一份"报 0 处"的门禁与一份"什么都不查"的
门禁在输出上无法区分，唯一的区分手段是拿已知违规去撞它。实测中 `check_no_literals.py` 的整数白
名单同时用于十进制与十六进制，而它豁免 0–64 —— opcode 恰好几乎都落在这个区间，于是
`{0x10: "CALL", 0x11: "JMP"}` 这类表整个通不报，一份四类违规的对照实现只报出一类。修正为
十六进制走独立的窄白名单（仅通用掩码）后同一对照实现报出全部四类，而受测的七个门禁脚本自身
仍报 0 处违规。**每次放宽白名单都要重跑阳性对照**：白名单是漏报的主要入口。

同理，`--no-asm`、`detailed=False` 一类跳过可选产物的开关，必须验证跳过后**核心门禁仍然执行**。
实测中首次加入 `--no-asm` 时因传入 `Path(".")` 占位值导致 264 个文件全部失败，由报告中的
`min_byte_coverage: 0.0` 暴露。此类开关的测试须断言自检仍已执行，而非仅断言命令未报错。

**证据等级**：`observed`（直接字节/运行时观测）> `derived`（确定性解析）> `inferred`（多证据
推断）> `unresolved`（开放问题）。`inferred` 永不能授权删除 `unknown_opaque_block` 或
`opaque-preserved`，也不能作为提级 tier 的唯一依据。`tag_source=heuristic` 等价于 `inferred`。

---

## 9. 零突变验证

```bash
python disassembler.py sample.sc -o sample.asm.txt
python assembler.py  sample.asm.txt -o sample.rebuild.sc
diff sample.sc sample.rebuild.sc          # 无任何差异
sha256sum sample.sc sample.rebuild.sc     # 必须一致
```

存在差异时修正方言或两侧解析逻辑，直至逐字节一致。**此步通过之前，禁止进入任何编辑流程。**
零编辑通过后，§8.2 的七个门禁脚本须全部返回退出码 0，方可视为交付合格。

**零突变只是起点，不是终点。** 它证明"不改时不坏"，但不证明"改了能用"。因此第二步必须验证
变长回封（§6.0.3）：

```bash
# 把若干条译文改长，再回封
python assembler.py sample.asm.txt -o sample.longer.sc
# 输出与原件长度不同 —— 长度相同才说明编辑未生效
# 但必须能被自身重新解析，且新文本确实在输出中
```

两步的判定方向相反，不可混用：零编辑要求哈希**相同**，变长要求哈希**不同**且输出仍然自洽
（§6.0）。只跑第一步的工具会在真实翻译任务的第一条超长文本上失效。

| 类别 | 必须跑通的用例 |
|---|---|
| 往返 | 零编辑黄金样本；同一输入跑两次结果确定 |
| Tier | 未定义 opcode 触发降级而非失败；T3 区间缺长度算法被拒 |
| 站点 | **值碰撞常量**：放一个值恰等于某文本条目偏移、但不在站点集合中的常量字，变长回封后逐字节不变，且计入 `preserved_value_collisions` |
| 站点 | 站点同构验证对「少一个站点」「多一个站点」两种注入故障都拒绝 |
| 死条目 | 删掉某键的全部站点，该条目仍在 IR 中并标 `unreferenced`，未被跳过或删除 |
| 文本篡改 | 改原文行 / 改 idx / 改 tag / 混用 `○●` / 删一行 / 交换两组 / 换文件头哈希 / 少交一片 / 改 `frozen` 条目——每种都被拒绝并报出精确位置 |
| 编码 | 不可解码字节往返逐字节一致、以占位符呈现、`frozen`；核心路径无 `surrogateescape`/`replace` |
| 占位符 | 逐字节回封一致；斜杠与全角空格未被转义成占位符 |
| 人名 | 同一 `msg` 两个名字候选时输出 `ambiguous` 与全部候选，而非任选其一 |
| 回封 | 零编辑选 `identity`；单条变长选 `pointer-rewrite` 而非 `full-layout`；`in_place` 超长被拒 |
| 回封 | 注入一个 probe 会通过但 run 必然失败的条件，验证系统停止而非降级 |
| **变长** | 译文加长若干字节后回封：输出可重新解析、覆盖仍为 1.0、校验和自洽、**新文本确实出现在输出中**、未编辑条目逐字节不变 |
| **变长** | 译文缩短后回封同样通过上述全部检查（缩短与加长走同一路径，不得只测其一） |
| **变长** | 长度差值等于各条目变化量之和加对齐调整量；出现无法解释的增减即失败 |
| **变长** | 批量场景下只编辑一个文件：该文件长度改变，其余文件**逐字节不变** |
| **哈希语义** | 零编辑时哈希必须相同；有编辑时哈希必须**不同**——编辑后哈希未变即判失败 |
| **容量** | 条目间存在对齐 padding 时，`in_place` 不得用相邻偏移相减当容量，probe 须返回 `CAPACITY_UNKNOWN` |
| **长度计算** | 含占位符的译文按展开后字节计；终止符计入容量；同一文本在 UTF-8 与 GBK 下得到不同的超长判定 |
| **双编辑面** | 只改 `texts/` → 成功，且 `asm.txt` 未被读取；只改 `asm.txt` 的字符串 → 成功，该串出现在输出中 |
| **双编辑面** | 两面改同一条且取值不同 → 拒绝并列出 idx 与两侧取值；取值相同 → 视为一致，正常执行 |
| **双编辑面** | 改 `asm.txt` 的指令而 tier 未达 T3 → 拒绝并说明所需 tier，不产出损坏文件 |
| **渲染确定性** | 同一源二进制两次渲染 asm 逐字节相同；改动渲染逻辑或做性能优化后哈希仍不变 |
| **不可编辑区** | 改动存储宽度、名称树填充槽位或共享子树 → 拒绝，而非尝试重建（§5） |
| **IR 落盘** | 默认运行后 `ir/` 不存在；`--with-ir` 后存在且 manifest 行区间可定位单源记录 |
| **IR 落盘** | 替换源文件后重跑，结果反映新文件——各阶段输入是源二进制，不存在陈旧缓存 |
| 方言 | profile 模块中机械搜索十六进制字面量与正则，零命中；缺 `evidence_refs` 的锚点被拒加载 |
| 报告 | `window_hits` 与逐规则命中数存在；`unresolved` 计数未被兜底规则吞掉 |
| 规模 | 超过 2 GB 样本按块处理；路径穿越、重复/缺失条目、关键层不可解均被拒并定位首个偏移 |
| **README** | 交付含 `README.md`；其报错清单与代码实际抛出的错误码逐条对应（多列或漏列均为缺陷）；不含 `decode_tier`/`unpack_mode`/`repack_strategy` 等内部概念；已知限制一节非空 |

---

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
- 每阶段收尾给编号选项：提级某区域、深挖某 unknown、加运行时 probe、导出、回封、或停在
  checkpoint。不提供隐藏的默认 Run-All。

---

以上 §10 及之前各节是**工程纪律**，面向实现者与报告。§11 是**使用者界面**，两者要求不同：内部
必须严格分级与留证，界面必须简单到不懂逆向的人也能用完。

---

## 11. run_gui.py：两按钮界面

### 11.1 设计原则

界面服务于「拿到游戏文件 → 翻译 → 装回去」的使用者，**不是逆向工程师的控制台**。

- **只暴露产出物，不暴露阶段。** 使用者关心的是「我要拿到什么文件」，不是「工具内部分几步」。
  反汇编、IR 构建、覆盖证书、往返自检全部在内部执行，界面不为它们设按钮。
- **不暴露内部概念**：`decode_tier`、`unpack_mode`、`repack_strategy`、`collision_class` 一律不
  出现在界面文字中。策略由 §6.2 的 probe 自动协商，界面只显示结果。
- **零配置可用**：拖入即推导全部路径，编码有默认值，不填任何参数即可运行。
- **路径可自定义**：懒人默认与显式指定并存，两者用同一套规则（§11.4）。
- **错误信息使用自然语言**：报「第 1204 条译文超长 6 字节，原文占 40 字节」，不报
  `LENGTH_OVERFLOW blocking_refs=[idx=00001204]`。技术细节收进「详情」折叠区与日志文件。
- **译文加长不得作为错误呈现。** 变长是本地化的常态（§6.0.1）：probe 判定 `in_place` 不适用时
  自动改用 `pointer-rewrite` 并照常完成，界面无需提示，「详情」中记录实际所用策略。

### 11.2 不设「全量反汇编」按钮

反汇编是产出任何文本的**前置条件**，不是使用者的目标。单独设按钮会造成三个问题：它不产出任何可用于
翻译的文件，使用者无从判断该不该点；「逐字节校验通过」对不懂逆向的人没有意义；不点则后续按钮不可
用，于是退化为必点的仪式。

规定：**反汇编在两个输出按钮内部各自执行**，无独立按钮、无中间文件。往返自检（§9）作为内部门禁
照常执行，失败时对应按钮直接报「此游戏暂不支持回封」。

这与铁律 5 不矛盾：**阶段隔离是实现层要求，按钮划分是界面层选择。** 两个按钮内部仍分别走结构解析
与语义判定两段，只是不要求使用者理解该区分。

### 11.3 布局

```text
┌────────────────────────────────────────────────────────────┐
│  游戏脚本文件夹                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  D:\Game\scn                              [浏览…]    │  │
│  │  把文件夹拖进来，或点此选择                          │  │
│  │  已找到 264 个脚本文件                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  原文编码 [cp932      ▾]     译文编码 [gbk        ▾]       │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  输 出 文 本                                         │  │
│  │  到 [D:\Game\scn_text                    ] [浏览…]   │  │
│  │  [✓] 双行文本（翻译用）   [ ] ASM 清单（改逻辑用）   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  回 封 文 本                                         │  │
│  │  从 [D:\Game\scn_text                    ] [浏览…]   │  │
│  │  到 [D:\Game\scn_rebuilt                 ] [浏览…]   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ████████████████████░░░░░░░  正在处理 aki003.txt.scn 72%  │
│  ✓ 已导出 66,334 条到 D:\Game\scn_text   [打开] [取消]     │
│                                                            │
│  ▸ 详情                                                    │
└────────────────────────────────────────────────────────────┘
```

单窗口，不用标签页、不用向导、不用多级菜单。两个操作各占一块，每块自带它需要的路径框——使用者
不必在一个全局设置区里推断哪个路径服务哪个操作。

### 11.4 三个路径与自动推导

界面只有三个路径概念，全部可改，且都有默认值：

| 路径 | 默认值 | 用途 |
|---|---|---|
| 输入 | 拖入或选择，无默认 | 源脚本所在文件夹（或单个文件） |
| 文本输出 | `<输入名>_text`，与输入**同级** | 双行文本与可选的 ASM 落地处 |
| 回封输出 | `<输入名>_rebuilt`，与输入同级 | 重建结果 |

```text
拖入 D:\Game\scn
  → 文本输出默认 D:\Game\scn_text
  → 回封输出默认 D:\Game\scn_rebuilt
  → 回封的「从」自动填为文本输出路径（改了文本输出，此处同步跟随）
```

四条规则：

- **默认输出与输入同级，不在输入目录内部。** 放在内部会让第二轮运行把上一轮产物当成新输入
  （§2.3 的输出目录排除规则可以挡住，但同级更不易出错，也便于整个文件夹交给译者）。
- **原始文件永不写入**（铁律 1）。回封产物一律进回封输出目录，由使用者自己复制回游戏。
- **回封的「从」默认跟随文本输出**，但可独立指定——译者可能把文本交回到另一个位置。
- 目标目录已存在同名产物时提示「覆盖 / 另存新目录」，不静默覆盖。

内部产物（覆盖证书、日志、`tmp/`、可选的 `ir/`）放在文本输出目录下的隐藏子目录，界面不展示
路径，「详情」里给完整位置。

### 11.5 两个按钮的行为

| 按钮 | 内部执行 | 界面显示 | 产出 |
|---|---|---|---|
| 输出文本 | 源 → 内存 IR → 覆盖证书 → **零编辑往返自检** → 按勾选项渲染 | 进度 + 条目数 + tag 分布 | `texts/` 与（可选）`asm/` |
| 回封文本 | 源 → 内存 IR → 对两个编辑面各做 diff（§2.6）→ 冲突检出 → 13 条导入校验（§4.9）→ probe 全部策略 → 选能力最小者 → run → 站点同构验证 | 所用策略、改动条数、长度变化、冲突数 | 回封输出目录下的重建文件 |

**两个按钮的输入都是源二进制**，各自解析出内存 IR（§2.4），互不依赖对方的产物。

#### 11.5.1 两个勾选项决定输出什么

```text
[✓] 双行文本（翻译用）    → texts/<镜像原路径>.txt
[ ] ASM 清单（改逻辑用）  → asm/<镜像原路径>.asm.txt
```

- **默认只勾双行文本。** 多数使用者只做翻译，不需要 571 MB 的 ASM 清单（实测 264 个文件）。
- 两项**可同时勾选**，此时一次运行产出两者，共用同一次解析。
- 两项**都不勾时按钮禁用**，并提示「请至少选择一种输出」——不产出任何东西的操作不应可点。
- ASM 是结构编辑面（§2.5）。勾选它意味着使用者要改指令或数据逻辑，界面上以「改逻辑用」说明，
  不解释 ASM 是什么。
- 无论勾选组合如何，**往返自检与覆盖证书照常执行**（§8.3）。跳过可选产物不得跳过核心门禁。

#### 11.5.2 回封读什么

回封只读文本输出目录下实际存在的文件：

```text
只有 texts/          → 仅应用文本改动，走 in_place 或 pointer-rewrite（T2）
只有 asm/            → 仅应用 asm 改动；改了结构则要求 T3
两者都有             → 各做一次 diff，交集处取值不同即冲突（§2.6 第四态）
两者都无             → 按钮禁用，提示「先输出文本」
```

**未改动的编辑面不参与 diff。** 按文件哈希判定：`asm/` 存在但与新鲜渲染一致时跳过 asm 分支，
省下一次渲染（实测约占单文件耗时两成）。

#### 11.5.3 回封前必须预览

按钮点击后**不直接执行**，先显示一次可取消的预览：

```text
将回封 264 个文件
  改动    1,876 条译文（其中 43 条变长，共 +2,104 字节）
  策略    引用回填（自动选择）
  冲突    0
  输出到  D:\Game\scn_rebuilt
                                        [执行] [取消]
```

有冲突时不显示「执行」，只列出冲突条目（idx 与两侧取值），要求使用者先处理。这是铁律 4 在界面上
的体现：歧义不得静默消解。

### 11.6 编码

两个下拉框，分别对应 §4.4 的 `source_encoding` 与 `target_encoding`：

- 预置常用项（`cp932` / `gbk` / `big5` / `cp949` / `utf-8`），允许手输任意 Python codec 名。
- 默认值取方言声明（`opcodelist.py`），缺省为 `cp932`。
- 选定后写入 `asm.txt` 头部与双行文本文件头，回封时自动复用，**使用者不需要选第二次**。
- 译文编码选错的典型后果是回封时大量字符不可表示。此时报「译文编码 `X` 无法表示第 N 条中的
  『字』，换 `Y` 试试」，并给出可表示该字的候选编码——不静默替换成 `?`（§4.4）。
- 双行文本文件本身固定 UTF-8 带 BOM（`text_encoding`），记事本打开不乱码；这一项**不暴露给
  使用者选**。

高级项收进「详情」区，默认折叠、默认关闭：

```text
▸ 详情
    [ ] 同时导出 IR（排查用，§2.4）
```

### 11.7 长任务与取消

- 解析在 Worker 线程或子进程中跑，**UI 线程不读大文件、不解码、不等同步 I/O**。
- 进度按已处理字节数报，附当前文件名；不显示不可信的剩余时间估计。
- 「取消」关闭 reader、删除 `tmp/` 下未提交的输出、保留日志与 checkpoint；**不删原件，不删已
  验证通过的产物**。
- 任一步失败：按钮回到可重试状态，错误摘要显示在进度条位置，完整信息进 `logs/` 与「详情」。
  失败不自动跳下一步（铁律 5）。
- 单个文件失败不中断整批：如实上报失败行，其余文件照常处理。

### 11.8 详情折叠区

默认折叠。展开后给只读信息，供出问题时贴给开发者：

```text
样本      SCRIPT.SRC  sha256 a1b2…  1,258,496 字节
理解深度  T2（已定位 1,284 个调用锚点）
覆盖      byte 100.00%   往返 逐字节一致
文本      2,041 条：可翻译 1,876 / 需确认 96 / 锁定 69
来源      结构 1,204 / 锚点 780 / 外观推断 57 / 未判定 0
回封方式  引用回填（自动选择）    改动 2 处范围 / 46 字节
内部产物  D:\Game\scn_text\_work\reports\coverage_certificate.json
```

「理解深度」是 `decode_tier` 的界面说法，只读、不可编辑、不作为选项。使用者无需理解它，出问题时
它是第一手线索。「来源」一行是 `tag_source` 分布（§4.3）：外观推断与未判定的条数必须可见，不得
并入其他计数。

### 11.9 实现约束

- GUI **不得自行解析二进制**，只能调用 `disassembler.py` / `assembler.py` 暴露的函数。同一操作
  经 GUI 与经命令行必须产出相同的 IR、产物和证书。
- 优先标准库 Tkinter（免装依赖，双击即用）；已有 Qt 依赖时可用 PySide6，两者共享同一批调用。
  Windows 上拖放用 `windnd` 或 `tkinterdnd2`，缺失时降级为「点击选择文件」并提示，不阻止启动。
- 单文件 `run_gui.py`，不建 `src/PACKAGE/gui/` 目录树。界面代码只做布局、取值、起线程、显示结果。
- 使用者不可关闭零编辑往返自检、不可抬高理解深度申报、不可越过 probe 的 `applicable=false`
  （§2.7 的 `user_override` 规则同样适用于界面）。
- **命令行必须提供与两个按钮等价的入口**，且阶段级命令（单独 disasm、单独 export-text）仍然保留
  供 CI 使用。界面简化不得削减命令行的可组合性。

### 11.10 GUI 验收

**路径与懒人默认**

- 拖入文件夹 → 两个输出路径自动填好，直接点「输出文本」即产出，全程未手填任何路径。
- 改文本输出路径 → 回封的「从」同步跟随；再单独改「从」→ 不被后续改动覆盖。
- 默认输出目录与输入**同级**，不在输入目录内部；第二轮运行不把上一轮产物当新输入。
- 目标目录已有同名产物 → 提示覆盖或另存，不静默覆盖。
- 原始文件在全流程中不被写入（可用只读属性或文件修改时间验证）。

**输出选项**

- 只勾双行文本 → 只产出 `texts/`，无 `asm/`；耗时低于同时勾选。
- 只勾 ASM → 只产出 `asm/`，无 `texts/`。
- 两项都勾 → 一次运行产出两者，且与分两次运行的产物逐字节相同。
- 两项都不勾 → 按钮禁用并提示。
- 任意勾选组合下**往返自检与覆盖证书均已执行**（断言自检已跑，非仅断言未报错）。
- 默认运行后无 `ir/`；「详情」里勾选后才出现。

**回封**

- 只改 `texts/` → 成功，且 `asm/` 未参与 diff（可用跳过渲染的耗时差异验证）。
- 只改 `asm/` 的字符串 → 成功，该串出现在输出中。
- 改 `asm/` 的指令而 tier 未达 T3 → 拒绝并说明所需 tier，不产出损坏文件。
- 两个编辑面改同一条且取值不同 → 预览显示冲突、不提供「执行」、列出 idx 与两侧取值。
- 两个编辑面改同一条且取值相同 → 视为一致，正常执行。
- 点击回封后先出预览，可取消；取消后无任何产物写出。

**文本变长**

- **把译文改成明显更长（例如原文的两倍）→ 正常完成**，自动改用变长策略，输出可载入运行，
  「详情」显示所用策略与长度变化量。这是本地化的主要用例，不得表现为错误。
- 只改一条译文 → 该文件长度改变、其余文件逐字节不变；不改任何译文 → 全部文件与原件哈希相同。
- 引用站点未完整解析的样本上尝试变长 → 明确告知不支持改变长度，且不产出损坏文件。
- 故意选错译文编码 → 报不可表示的具体字符并给候选编码。

**其他**

- 往返自检失败时「回封文本」保持禁用，并明确告知「此游戏暂不支持回封」。
- 处理中途点取消 → `tmp/` 清空，原件与已验证产物完好，日志保留。
- 缺拖放依赖时仍能启动并用「选择文件」完成全流程。
- 同一输入经 GUI 与命令行产出的证书哈希一致。
- 单个文件失败不中断整批，失败行如实上报。

---

## 12. 性能：纯 Python 也能跑快

批量几十上百个脚本时，慢通常不在算法复杂度，而在**每字节都进了一次 Python 解释器**。以下按收益
从大到小排，前四条是数量级差异，必须做。**任何优化都不得降低 §8 的证书要求或 §9 的往返一致性。**

### 12.1 一次性预计算，不要在循环里重算

应置于热循环外的对象：`struct.Struct` 实例（不要反复调 `struct.unpack` 传格式串）、锚点掩码与模式
（预编译成整数对）、方言查表（dict 而非 if/elif 链）、编解码器对象（`codecs.lookup` 一次）、
锚点值集合（`set` 而非 `list`，`in` 从 O(n) 变 O(1)）。

批量作业中这些**整个作业只做一次**，不是每个文件一次。方言解析、锚点编译、编码探测、正则编译
全部提到循环外——几十个文件就是几十倍的重复开销。

### 12.2 批量解包代替逐单元读取

这是最大的一笔。定长单元流（T1）不要逐个 `struct.unpack_from` 循环：

```python
# 慢：每个 cell 一次 Python 调用，1 MB 文件 = 262,144 次
words = [struct.unpack_from("<I", data, i)[0] for i in range(0, len(data), 4)]

# 快：一次 C 层调用完成全部转换
import array, sys

if len(data) % 4:                       # §1.2：不整除即解析失败，不得截断或补齐
    raise CellAlignmentError(len(data))
words = array.array("I")
words.frombytes(data)
if sys.byteorder != "little":           # 目标是小端；宿主为大端时翻转
    words.byteswap()
```

CPython 3.11 实测：1 MB 约 121 倍（33.2 ms → 0.27 ms），8 MB 约 229 倍（257 ms → 1.12 ms），
结果与逐个 `unpack_from` 逐元素相等。

**`array.array` 与 `memoryview.cast("I")` 不等价，别混用**：`memoryview.cast` 没有 `byteswap`
方法（实测 `hasattr(mv, "byteswap") is False`），它只按**宿主**字节序解释，因此只有在目标字节序
恰好等于宿主字节序时才正确。规则：

- 需要跨平台确定性 → 用 `array.array` + 显式 `byteswap`（上面的写法）。
- 只读且已确认目标字节序 == 宿主字节序 → 可用 `memoryview.cast`，零拷贝更省内存，但必须在代码里
  断言这个前提。
- 两者都不能替代「显式声明目标字节序」这件事：字节序来自方言声明（§7 的 `endianness`），不是从
  宿主推断。在大端机器上跑小端样本必须得到相同结果，这是 §8「同一输入跑两次结果相同」的跨平台
  推论。

需要切片视图时用 `memoryview` 而非 `bytes` 切片——前者零拷贝，后者每次复制。

### 12.3 用集合交集做候选筛选，不要嵌套循环

引用连接（§3）的朴素写法是「对每个字，查它是否等于任一条目偏移」，即 O(字数 × 条目数)。正确写法
是一次哈希 join：

```python
# 目标身份键建 set（一次）
key_set = {e.entry_offset for e in entries}

# 用 set 交集先粗筛，再只对命中的字做完整验证（对齐/范围/锚点/密度，§3.2）
hit_values = key_set & set(words)          # C 层集合运算
sites = [(i * 4, w) for i, w in enumerate(words) if w in hit_values]
```

先用集合把候选压到极小，再对候选逐个跑 §3.2 的四条验证。**粗筛只是加速手段，不得省略四条验证**
——省了就退化成「值相等即命中」，正是 §3.2 禁止的。

同理，锚点匹配先用 `set` 交集定位候选偏移，再在候选处做掩码比对，而不是全流滑窗。

### 12.4 I/O：一次读入，顺序写出

- 单文件一次 `read()` 进内存（几 MB 的脚本无需流式）；超过约 64 MB 或需要随机访问时用
  `mmap.mmap`，让 OS 页缓存接管，避免自己实现分块逻辑。
- 输出用**单个** `open()` + 缓冲写，累积 8-64 KB 再落盘；不要每条记录 open/close 或 flush。
- JSONL 用 `"\n".join(...)` 批量拼接后一次写，而不是逐行 `write`。
- 合库布局（§2.3）本身就是 I/O 优化：几十个源共用一组文件句柄，而非几百个小文件的
  open/close/fsync 风暴。
- 序列化热点用 `json.dumps(obj, separators=(",", ":"), ensure_ascii=False)`（省去缩进与空格的
  生成开销）；若 `orjson` 可用则优先，但**必须在缺失时回落标准库**，不得成为硬依赖。

### 12.5 数据结构：别为每条记录建对象

几十万条指令/单元时，每条一个普通 `dict` 或普通类实例的内存与构造开销都很可观：

- 热路径的记录类型用 `@dataclass(frozen=True, slots=True)` 或 `NamedTuple`——`slots` 省掉每实例
  的 `__dict__`，属性访问也更快。两字段实例实测 48 字节，无 slots 则是 56 字节实例加 288 字节
  `__dict__`，约 7 倍差距；几十万条记录时这就是几百 MB 的差别。
- 更热的场景（cell 流、站点集合）直接用**平行数组**（`array.array` / 列表）而非对象列表，按索引
  访问，只在导出时物化成记录。
- 大量重复的短字符串（tag、编码名、方言 ID）用 `sys.intern`，让比较退化为指针比较。
- 反复查的映射一律 dict/set；**不要**在列表上做 `in` 或线性查找。

### 12.6 并行：按源文件切分

反汇编各源之间无依赖，天然可并行。**用 `ProcessPoolExecutor` 而非线程**——解析是纯 CPU 计算，
受 GIL 限制，多线程不会变快：

```python
with ProcessPoolExecutor() as pool:
    for src_id, partial in pool.map(disasm_one, sources, chunksize=8):
        merge_into_library(src_id, partial)      # 主进程串行合库
```

约束：

- 每个 worker 返回**该源的记录段**，由主进程串行写入合库，避免多进程争抢同一文件导致交错。
- 子进程只收「路径 + 方言 + 选项」这些可 pickle 的小对象，不传 reader、句柄或大 buffer。
- `chunksize` 取 4-16，避免每个任务一次 IPC 往返。
- 文件数少（少于约 8 个）或总量很小时**退回单进程**——进程启动成本会盖过收益。
- 输出顺序必须与源顺序无关：合库后按 `src_id` 排序，保证 §8 要求的「同一输入跑两次结果相同」。
  并行不得引入任何非确定性。

### 12.7 先测量，再优化

优化前先定位。`python -X importtime` 看启动开销，`cProfile` + `pstats` 定位热点，
`time.perf_counter()` 打点分段耗时。报告里给出各阶段耗时与吞吐（MB/s、条目/s），便于回归对比。

**禁止**为了性能做这些：跳过 `raw_sha256` 计算或校验、跳过零编辑往返自检、用采样代替全量覆盖
检查、缓存跨作业的解析结果而不校验源哈希。性能问题的正确解法是上面六条，不是削减验证。

### 12.8 先删冗余计算，再谈优化技巧

上面六条解决**如何加快必要的工作**；实测收益最大的一项是**删除不必要的工作**，它只需确认每一步
实际证明了什么。实例——反汇编阶段 30% 的时间花在自检的第二轮：

```python
rebuilt   = repack(doc)
identical = rebuilt == data
doc2      = parse(rebuilt)     # identical 为真时，这是在解析同一批字节
again     = repack(doc2)       # 故 again == rebuilt 恒成立
stable    = again == rebuilt   # 恒为 True，未提供任何信息
```

`parse` 确定，`rebuilt == data` 时第二轮输入与第一轮完全相同，结论必然相同——该段代码在证明恒等式。
改为仅在 `identical` 为假时执行（那时它确实提供信息），单文件由 3.6 秒降至 2.5 秒。

**排查清单**——每一项都在实测中命中过：

```text
□ 该校验在其成立的分支内是否恒真？（如上：先判 identical 再决定要不要第二轮）
□ 同一个纯函数是否被算了两次？（byte_coverage() 内部重复调用 analyze()）
□ 循环里是否有恒定表达式？（`(size_of or {})` 为十万级节点各建一个空字典）
□ 是否为了一个探针把整个文件读了第二遍？（read_bytes() 与 load() 各读一次）
□ 产出的数据有没有人读？（逐节点 checks 字典只有覆盖证书用，批量流程不出证书）
□ 去重集合是否与已有检查重复？（区间 ID 集合与 overlap 检测等价）
```

最后一类最隐蔽：**为"更严格"而加的检查，可能与另一处检查等价**。判断方法是构造反例——若"能触发
A 但不触发 B"的输入不存在，A 就是冗余的。区间 ID 去重就是这样被证明多余的：ID 相同意味着区间与
kind 全同，`analyze()` 的重叠检测必然命中同一处。

删除冗余与加速优化的**顺序不可颠倒**：先删除不应执行的步骤，再优化其余部分。顺序颠倒会导致
对本不应存在的代码投入优化。

### 12.9 性能验收

- 批量 50 个源与单独跑 50 次相比，总耗时显著更低，且产出的证书哈希完全一致。
- 并行与单进程产出逐字节相同的 IR 与证书。
- `ir/` 的文件数不随源文件数线性增长（合库生效）。
- 重复内容的 blob 在 `blobs/` 中只存一份。
- 关闭全部可选加速依赖（`orjson` 等）后仍能正确运行，仅速度下降。
- **每一处优化都验证过输出不变**：改动序列化或遍历顺序后，产物哈希必须与优化前逐字节相同。
  实测中 ASM 清单的 SHA-256 在四轮优化前后保持一致，这是"只改快慢、不改结果"的唯一证据。
