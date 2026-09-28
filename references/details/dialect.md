> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

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

**硬规则：引擎特定魔数/opcode/调用ID/分类正则须声明化。** 字面量扫描用于初筛，
通用掩码、产物语法等不能仅凭外观判违规，须核对用途与豁免理由。

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
        0x10: {"mnemonic": "CALL", "length": 6,
               "operands": [{"type": "sub_opcode", "bits": 8},
                            {"type": "rel_offset", "bits": 32, "base": "instruction_end"}],
               "sub_opcodes": {0x00: "PRINT_TEXT", 0x01: "PLAY_SOUND"},
               "evidence_refs": ["EV_CALL_TABLE"], "confidence": "derived"}},

    "text_rules": [
        {"id": "font-family", "subtype": "font-family-name",
         "requires_callee_group": "font",     # 前置：已由锚点证明为文本参数
         "predicates": [{"kind": "max_length", "value": 12},
                        {"kind": "contains_script", "value": "cjk-or-kana"}],
         "tag": "misc", "tag_source": "unresolved", "confidence": "inferred"}],
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
    matched = [s for s in dialect.entry_shapes if s.matches(doc, entry_off)]
    if len(matched) > 1:
        raise AmbiguousEntryShape(offset=entry_off, candidates=[s.id for s in matched])
    if matched:
        return matched[0].extract(doc, entry_off)
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
□ 既有样本条数、内容、角色、绑定不变；若修复旧漏提，记录预期差异后更新基线（历史例66,334条）
□ 全部既有样本的零编辑往返仍逐字节一致
□ 新样本的 ASM 与 IR 哈希可复现（同一输入两次运行结果相同）
□ 新旧样本的形态签名分布均记入报告，可对比
□ 新增形态的分支被实际命中（覆盖率非零，否则声明形同虚设）
```

最后一条防止一类隐蔽失败：新增了形态声明，但判定条件写错导致从未命中，而既有分支恰好"成功"
返回空结果——此时全部门禁通过，提取结果依然是错的。

---

