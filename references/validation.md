# 可执行验证协议

当前CLI/schema在本篇集中维护；同时保留 [完整覆盖证书/门禁说明](details/gates.md)
及 [完整正负例验收矩阵](details/verification.md)。新增接口不意味着删掉原交付验收要求。

适用：调用本包门禁、接入 CI、生成临时验证快照、解释结果。
返回 [主流程](../SKILL.md)。门禁不是解析器，也不能从自报统计证明真实样本已被正确理解。

## 1. 状态、范围与证据

| status | ok | 进程退出码 | 含义 |
|---|---|---|---|
| pass | true | 0 | 该工具明确声明的检查范围通过 |
| fail | false | 1 | 输入非法、约束违反或协议不一致 |
| not_verified | false | 2 | 没有足够输入/证据完成所请求的检查 |

CLI 帮助不是验证事件；命令行用法错误、运行器崩溃或非 JSON 输出也不能作为通过。
报告中的 advisory 需要审阅，但不是已证实错误。某子能力未验证时不能由外层 pass 推导其成立：
例如“文件确实改变”可以 pass，`semantic_correctness` 仍未验证。

**结果是带范围的命题，不是整个项目的通过证。** 对本次验收确属必需但缺失的检查，
总报告应为 not_verified；对于本次完全不适用的检查，在计划中记录原因，不能伪装为已执行。

报告/快照来自同一解析器时存在共同盲区。高风险改写应增加独立结构约束、不同来源语料或运行时对照。
形态统计、产出条数不变都只是必要证据；角色、内容、绑定、引用以及未编辑对象仍应比较。

## 2. 默认不保存 IR 也能运行门禁

内存 IR 是正常工作方式，不要求为每个源生成持久 JSON。
需要独立 CLI 检查时，在独立临时验证目录生成最小快照：

```text
validation/
  ir/manifest.jsonl
  ir/text_entries.jsonl
  join_sites.jsonl
  layout-map.jsonl             变长/重排时
  rebuilt-sites.jsonl          要求站点同构时
  gates.json
```

快照绑定当前源哈希、src_id、解析器/方言版本；不能复用未校验来源的旧 IR。
不要把 IR 快照写入输入扫描目录。失败保留快照与完整命令，成功后可清理；
用户要求持久审计时再导出。未请求 ASM 不需要生成两份 ASM 来凑验证材料。
只提取的任务不要求实现回封器，但必须明确未验证回封与运行时加载。

## 3. 七个门禁的输入和证明边界

### 3.1 双行文本：check_dsat.py

```bash
python scripts/check_dsat.py validation/ir texts/
python scripts/check_dsat.py validation/ir part1.txt part2.txt --report reports/dsat.json
python scripts/check_dsat.py validation/ir texts/ --target-encoding cp932
```

- `manifest.jsonl`：每行对象，`src_id` 非空、唯一，`sha256` 为 64 位十六进制。
  兼容 `src_sha256` 别名；二者同时给出必须相同。同哈希多源需投影头显式给 `src_id`。
- `text_entries.jsonl`：每行 `src_id, idx, source, tag, translate_policy`。
  idx 为非负整数且源内唯一；source 为精确原文字符串；tag 为闭集；
  policy 为 `translatable/length-locked/review-required/frozen`。
- `length-locked` 另需可信 `raw_len`；可选 `slot_capacity` 是本次策略确实要求固定容量时的约束，
  不要用旧槽容量自动拒绝已经支持重定位的翻译。
- 缺 manifest 时，唯一源可供局部检查，但来源哈希未核验，结果为 not_verified。
- 读入 TEXT/1、TEXT/2；四行头依次为版本/来源、encoding、scope、tags。
  默认 idx 宽度 8，`--idx-width` 可显式变更。标签以 IR 为权威，而不是三个文本行彼此一致就够。
- 注释里的 policy 只能与 IR 核对，不得覆盖。review-required 的实际修改须有 `reviewed=true`；
  这是显式确认记录，不代表脚本认证了确认人的真实身份或资格。
- 完整导入验收从可信作业配置传 `--target-encoding CODEC`；按规范 codec 名核对投影头，
  别名如 utf8/utf-8 等价。未传时仍可验证“按头声明的编码是否可表示”，
  但报告 `encoding_binding=not_verified`，不能把该局部 pass 当成游戏目标编码已绑定。
- 完整导入检查各片条目并集及交集；目录为空、重复条目、漏条目、重复分片均不能通过。
  部分导入须由调用方传入明确期望范围，不允许仅修改文本头将完整任务缩小。

部分导入使用 `--expected-scope validation/scope.json`；
文件内容为 `{"scene":[1,3]}` 这样的 src_id → 非空、无重复整数 idx 数组。
文本头可写 `kind=idx-range range=1-3 part=1/1`，但该范围内真实 IR 条目集合、
提交条目集合与授权集合三者必须相等（若 idx=2 确实存在，就不能用这个范围表示仅 1 和 3）。
多个区间可分文件提交；每个被授权的源都必须提交，不接受缺源后仍称完整。

最小 TEXT/2 示例：

```text
# TEXT/2 ir=1 tool=1 src_sha256=SOURCE_SHA256 src_id=scene
# encoding source=utf-8 target=utf-8 file=utf-8
# scope kind=all range=ALL part=1/1
# tags name msg choice label ui system ruby misc
# idx=00000001 tag=msg
○00000001○msg○原文
●00000001●msg●原文

```

`SOURCE_SHA256` 需替换为真实源哈希。机器元数据是无空白的 `key=value`；
说话人的完整显示可用人读注释，真实绑定仍来自 IR。
内置门禁保护已登记的字节占位符顺序和值；不实现任意格式的 tokenizer、
ASM 编译器或游戏编码器。高级 token 协议见 [编辑面契约](projections.md)，不能默认已有实现。

### 3.2 站点、布局和归因：check_sites.py

```bash
python scripts/check_sites.py original.bin rebuilt.bin validation/join_sites.jsonl
python scripts/check_sites.py original.bin rebuilt.bin validation/join_sites.jsonl --layout-map validation/layout-map.jsonl --rebuilt-sites validation/rebuilt-sites.jsonl
```

站点 JSONL 每行至少 `site_offset, key_value`；显式推荐给出 `site_width`（1/2/4/8）、
`site_endianness`（little/big）、`rewrite_policy`（rewrite/preserve）。
变更时给 `new_key_value`，站点本身移动时给 `new_site_offset`。
数值接受非负整数或十进制/0x 字符串，不接受 bool；同一文件的站点不能重叠。
合库记录须按源过滤，不能混合多个 src_id 当成一个地址空间。

等长比较要求**每个改动字节被允许区间并集完整覆盖**；部分相交不足以归因。
允许区间和站点列表是声明，不是目标结构已被正确理解的证明。
旧值在非引用位置出现的保护检查也是结构验证的补充，不能替代独立重解析。

布局 JSONL 每行：

```json
{"old_offset":0,"old_length":16,"new_offset":0,"new_length":16,"kind":"preserve"}
{"old_offset":16,"old_length":8,"new_offset":16,"new_length":12,"kind":"changed","reason":"text object S2"}
```

old/new 各自都必须完整覆盖对应文件空间，无缺口、无重叠；
preserve 段要求逐字节相同，changed 段必须有原因。
此示例只适用于源长 24、新文件长 28 的对应布局，不能照抄到其他样本。
源与新文件长度不同但未提供可靠映射时，必须 not_verified，不能跳过归因再宣称严格成功。

`--rebuilt-sites` 接受同类站点记录，检查申报的新站点集合与重解析记录一致；
未提供时只检查声明站点，不宣称站点发现完整。仍需适配器核对目标对象、长度字段和语义值。
不再隐式识别某引擎布局或内置 AOSv2 头偏移。压缩/加密后的归因应在适当逻辑层运行，并另验封装层。

### 3.3 产出合理性：check_output_sanity.py

支持单对象、非空对象数组、`rows/samples/files` 包装或 JSONL。样本身份用
`sample`（兼容 file/name/path）；重复身份拒绝。推荐写法：

```json
{"sample":"scene.json","byte_size":2048,"domain":"dialogue-scene","required_tags":["msg"],"tags":{"msg":12,"name":2}}
```

`tags` 的数量是非负整数，禁止负数、bool 和非有限数；缺统计不等于零，也不等于通过。
空报告拒绝。合法的“此资源没有文本”可用 `allow_empty={reason,evidence_refs:[...]}` 审计说明。

```bash
python scripts/check_output_sanity.py reports/extract.json
python scripts/check_output_sanity.py reports/extract.json --domain dialogue-scene --require-tag msg
```

默认没有普适的 msg 必需条件。仅在已知含正文的域/样本上声明必需类别；
不可把文件夹里每一个 UI 或资源文件都按剧本正文验收。
95% 偏斜和每 KB 密度变化默认 advisory，零计数显式写出或省略不改变结论。
`containers` 是可选的同类数量对照，缺它不宣称做过量级比较。
`--allow-zero TAG` 必须有每样本 `waivers[TAG]={reason,evidence_refs:[...]}`，不能无证据关闭门禁。

### 3.4 形态与语料枚举：check_shapes.py

```json
{"declared":["flat-v1"],"observed":{"flat-v1":{"entries":12,"texts":12}},"unmatched":{}}
```

declared 为无重复字符串数组；observed 的 entries/texts 为非负整数。
兼容旧的单一 entries 数量写法，但缺 texts 时为 not_verified。
没有正数观测不能证明枚举完成。未声明形态、未解析正数条目或没有解释的“有条目无文本”须处理。
非文本结构可通过 `nontext_shapes[shape]={reason,evidence_refs:[...]}` 明确说明。

```bash
python scripts/check_shapes.py reports/shapes.json --baseline reports/previous-shapes.json
python scripts/check_shapes.py reports/shapes.json --corpus-wide --corpus-manifest validation/corpus.json
```

语料清单是非空 `[{sample,sha256}, ...]`。报告另含
`corpus={manifest_sha256:清单文件真实哈希,scanned:[{sample,sha256},...]}`；
脚本核对清单哈希及身份集合，缺项/多项/换样本不能仅凭 `--corpus-wide` 放行。
但脚本不能独立证明所报 scanned 来自真正解析；执行日志及解析器测试仍需保留。
继承但本批未命中的形态通过 `inherited[shape]={reason,evidence_refs:[...]}` 声明，
不是把 unused 统计删除。回归除了条数还应比较内容与角色，修正旧漏提时允许带证据更新基线。

### 3.5 字节覆盖证书：coverage_certificate.py

输入 JSON 至少含 `source_size` 与有序 `intervals`；
每区间含 `id,start,end,status,raw_sha256`。
区间为半开区间，完整覆盖真实源文件，哈希从实际源区间复算。
status 支持 decoded、structured-unknown、unknown_opaque_block、opaque-preserved、padding；
proven-gap 不算完整保真。重复键/ID、越界、缺口、重叠、错误哈希均拒绝。

`byte_coverage` 若提供须与复算值相等；`structural_coverage` 是不同的自报指标，
不能因为字节全覆盖就判定它也应为 1。空的真实文件可有空区间覆盖，但不能冒称已验证结构。

没有理解等级字段时只检查字节证据，并明确 `tier_claims_checked=false`。
提供 tier 时各区间须填合法 T0..T4；`tier_coverage` 为各等级的**字节数**，
`min_tier/declared_tier` 是全源最低等级统计，不是本次操作能力的全局否决项。
证据表 `evidence[id]={kind,source}` 与 `tier_evidence_refs` 必须可解析；
高等级需与其声明的单元/边界、结构字段或锚点、指令、CFG 字段一致。
固定单元路线给 cell_size/cell_count/endianness；结构或变长指令用显式 boundary_model
和对应边界证据，不伪造固定宽度。数值 instruction_coverage 的本脚本口径是
T3/T4 区域字节数占全源字节数的比例，不由全文件最低 tier 决定。
能力清单若使用 `capability_scopes[capability].scope_region_ids`，按受影响区域验证等级前提。
identity/roundtrip 允许 T0；full-layout 的 scope.operation_kind 默认 data，仅检查数据布局的 T2 前提，
指令布局须显式 instruction 并满足 T3；这不授权指令插删或控制流变更。
即使字段一致，也只能证明**声明自洽**，不能代替审阅证据内容或重新逆向。

### 3.6 恒等与确定性：check_determinism.py

```bash
python scripts/check_determinism.py rerun first.txt second.txt
python scripts/check_determinism.py edit source.bin rebuilt.bin --no-edit
python scripts/check_determinism.py edit source.bin rebuilt.bin --edited
```

rerun 接受成对文件或目录，比较实际字节。空比较集合不能证明执行过渲染。
no-edit 要求源与输出逐字节一致；edited 要求确有字节变化，不要求长度变化，
也不证明变更符合预期。改变一字节的损坏文件同样可能满足 edited，必须另外核对语义。

### 3.7 方言字面量扫描：check_no_literals.py

```bash
python scripts/check_no_literals.py implementation/ --exclude opcodelist
```

检查 AST/字面量特征，输出硬命中及 advisory；这是启发式，不是通用架构证明。
测试夹具、方言声明及扫描器自身不属于通用解析核心扫描范围；零匹配文件为 not_verified。
不要为了“清零”机械搬动所有数值/正则。通用常量有合理原因时可在该行用
`# dialect-literal-ok: 具体理由` 记录审阅，不以空注释或宽目录排除掩盖真正魔数。

## 4. 聚合器：每项适用性显式记录

`run_gates.py` 只运行七个已知门禁，参数数组不经过 shell。
计划中每个门禁必须至少有一项 check 或一个 not_applicable 原因，不能悄悄漏掉。
同一门禁可有多项不同源检查，id 唯一；全部不适用/空 checks 不算验证。
相对文件路径以计划所在目录为基准，不以当前终端目录为基准。

```json
{
  "schema_version": 1,
  "scope": "仅验证这一对文件的零编辑恒等",
  "checks": [
    {"id":"identity","gate":"check_determinism","args":["edit","source.bin","rebuilt.bin","--no-edit"]}
  ],
  "not_applicable": {
    "check_dsat":"本轮未提交文本导入",
    "check_sites":"本轮未提交编辑或重定位",
    "check_output_sanity":"本轮不评估提取",
    "check_shapes":"本轮不评估形态枚举",
    "coverage_certificate":"本轮只比较字节，未申报覆盖证书",
    "check_no_literals":"本轮无解析器代码变更"
  },
  "timeout_seconds": 120
}
```

这个示例只证明 identity，不能当成完整回封验收。每个检查记录真实 command、cwd、stdout、
stderr、exit_code、子报告；超时/启动失败为 not_verified，状态与退出码不一致为 fail。
存在 fail 则聚合 fail；否则存在 not_verified 则聚合 not_verified；其余才 pass。
“不适用”的判断也需要审阅，不能为通过而删去实际必需的验证。

## 5. 门禁维护与迁移

运行 `python -B -m unittest discover -s tests -v`。
新增限制先给负例与邻近正例，包含编码、空集合、分片、重复键、缺证据和变长映射。
保证输出报告路径不能覆盖其输入；失败应是可读诊断而非无解释的 traceback。

旧 TEXT/1、旧统计字段可在不降低可信权限的前提下读入；缺少新要求的证据时明确 not_verified。
新增字段不是默认事实。修复历史错误导致结果变化时，记录为什么变化并更新回归基线；
不得为了保持旧哈希而保留已证实的错误结果。
