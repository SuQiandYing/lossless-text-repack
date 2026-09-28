> **完整规格，不是摘要。** 保留对应原章节、布局、代码和验收；仅登记的技术错误被校订。
> [章节/保全清单](../PRESERVATION.md)；[当前CLI与schema](../validation.md)。历史实测数字是原文案例，非本次重测。

## 3. 引用连接：跨对象文本发现与重定位

内联文本可以由已解析的结构字段证明；跨对象文本用已证明的引用连接发现。
扫描只提供待证候选，不能直接授权。引用连接是源槽位值与目标结构身份键之间可验证的等值关系。

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
仅单一提取器命中时复核缺少共识的原因；已有独立结构/宿主证据可支持 derived，不机械按提取器数量降级。

---

