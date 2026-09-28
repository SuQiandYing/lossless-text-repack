> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 6. 回封策略：由 tier 决定，不是用户偏好

| 策略 | 最低 tier | 允许的变化 | 必须已解析 |
|---|---|---|---|
| `identity` | T0 | 无（零编辑往返） | 原始字节区间可原样保留 |
| `in_place` | T2 | 编辑后字节数 ≤ 原槽容量 | 每个文本槽的起止与容量 |
| `pointer-rewrite` | T2 | 文本任意变长，引用槽原地回填 | 全部引用站点集合 |
| `full-layout` | 数据 T2 / 指令布局 T3 | 结构重排、跨层尺寸变化；控制流/指令增删需T4 | 全部指针/跳转/表容量/校验依赖 |

`identity` 是其余策略的前置：**未通过零编辑往返，禁止进入任何编辑流程。**

改动来自哪个编辑面（§2.5）决定所需策略：

| 改动来源 | 所需策略 | 所需 tier |
|---|---|---|
| `texts/` 的 `●` 行，编码后未超容量 | `in_place` | T2 |
| `texts/` 的 `●` 行，编码后超出容量 | `pointer-rewrite` | T2 |
| `asm.txt` 的字符串行（`.string`） | 等同文本改动，按上两行处理 | T2 |
| `asm.txt` 的数据结构 / 指令布局 | `full-layout` | 数据 T2 / 指令 T3；指令增删/控制流 T4 |
| 两个编辑面均无改动 | `identity` | T0 |

纯数据布局不要求伪造指令；指令布局与控制流改动分别要求对应证据。工具绑定源哈希及编辑对象，
遇到影响闭包证据不足时拒绝并指出缺项（TIER_TOO_LOW），而不是先尝试生成疑似损坏文件。

### 6.0 三条不可混淆的语义

```text
零编辑回封  未修改任何条目            输出与原件逐字节相同，三种哈希相同
等长回封    已修改但编码后未超容量    哈希必然改变，总长度不变
变长回封    修改后超出原容量          相关布局与引用重新计算，总文件长度可能不变
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
□ 站点集合与原集合同构：稳定站点身份一一对应，物理偏移按布局映射核验
□ 每处已编辑条目的新内容确实出现在输出中
□ 未编辑条目的字节内容逐条不变
□ 对应未压缩层解释条目/元数据/对齐增量；封装后另验存储大小，不跨层套用明文求和公式
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
reason_code ∈ {OK, EDIT_PRESENT, TIER_TOO_LOW, LENGTH_OVERFLOW, UNRESOLVED_JOIN_SITE, AMBIGUOUS_JOIN_KEY,
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
   {"strategy_id": "identity",        "applicable": false, "reason_code": "EDIT_PRESENT",
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
- **同构验证**：输出重新解析后，稳定站点身份、key_kind 与目标对应；key_value 和 site_offset
  按各自布局映射核对。未授权的新增/消失须拒绝并保留失败样本。

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

