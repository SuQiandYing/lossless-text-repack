> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 8. 覆盖证书

```json
{"schema_version": "1.1.0", "layer_id": "L000", "source_size": 0,
 "intervals": [], "gaps": [], "overlaps": [], "status_counts": {},
 "byte_coverage": 1.0, "structural_coverage": 0.0,
 "tier_coverage": {"T0": 0, "T1": 0, "T2": 0, "T3": 0, "T4": 0},
 "min_tier": null, "declared_capabilities": [],
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

### 8.1 严格成功的必要验证条件

```text
□ 区间恰好覆盖 [0, source_size)，首段从 0 起、末段止于 N
□ 无 gap / overlap / proven-gap
□ 每段 raw_sha256 可从源按范围流式复算
□ tier_coverage 各值之和 == source_size；min_tier 与区间中的最低 tier 一致
□ declared_capabilities 的作用域区域满足门槛，并证明影响闭包依赖（§1.3）
□ 数值 instruction_coverage = T3/T4 区域字节数 / 全源字节数；无指令可 not_applicable
□ byte_coverage == 1.0；structural_coverage 独立申报定义，不由字节覆盖推定
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

七个门禁的本次适用项须真实通过；不适用须列原因，必要但未验证不能算通过。以下保留所有调用入口：

```console
python scripts/check_output_sanity.py reports/extract_report.json
python scripts/check_shapes.py        reports/shapes.json --corpus-wide \
                                      --baseline reports/shapes_baseline.json --corpus-manifest validation/corpus.json
python scripts/check_determinism.py   rerun asm/A.asm.txt asm/A.asm.run2.txt
python scripts/check_determinism.py   edit SAMPLE rebuilt/SAMPLE --no-edit
python scripts/coverage_certificate.py SAMPLE reports/coverage_certificate.json
python scripts/check_dsat.py          validation/ir/ texts/ --target-encoding cp932
python scripts/check_sites.py         SAMPLE rebuilt/SAMPLE validation/join_sites.jsonl \
                                      --layout-map validation/layout-map.jsonl --rebuilt-sites validation/rebuilt-sites.jsonl
python scripts/check_no_literals.py   SRC_DIR --exclude opcodelist
```

| 脚本 | 守住的规则 | 拒绝的情形 |
|---|---|---|
| `check_output_sanity.py` | §0.1 产出合理性 | 证据支持的必需类别缺失/数量级失配；95%偏斜及密度变化为advisory |
| `check_shapes.py` | §0.2 / §7.1.5 形态穷举 | 观测到未声明的形态、声明的形态从未命中、形态匹配了条目却产出 0 条文本、形态分布相对基线漂移 |
| `check_determinism.py` | §2.6 渲染确定性、§6.0 哈希语义 | 两次运行产物不同、零编辑却哈希改变、**有编辑却哈希未变** |
| `coverage_certificate.py` | §8 区间、哈希、gap/overlap | 缺口、重叠、哈希不符、覆盖率不足 |
| `check_dsat.py` | §4.6/§4.9已实现输入契约，范围见validation.md | 原文/tag/权限/分片/占位符/编码等；不宣称实现任意引擎终止符语义 |
| `check_sites.py` | §6.3 站点及字节范围检查 | 站点值错、映射/保持区损坏、完整差异覆盖失败；同构需重解析站点输入 |
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
- `check_sites.py` 等长用允许区间并集完整覆盖每个改动字节；变长提供 old/new 布局映射，
  preserve段逐字节核验，changed段记录原因。缺映射返回not_verified/2，
  不再以计数法或跳过归因当成功；同构检查另需 --rebuilt-sites。
  完整当前schema与参数见 references/validation.md。

七个脚本只读输入，JSON报告，退出码 pass=0 / fail=1 / not_verified=2，可接CI/unittest。
不得为通过而削弱规则；修正规则必须同时更新文档和正负对照。

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

以下保留原文的历史校准案例，不等于本次重新执行过该语料；当前结果以实际回归测试为准。
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

