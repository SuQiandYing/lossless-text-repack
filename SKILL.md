---
name: lossless-text-repack
description: "逆向游戏脚本、字节码与资源归档，构建可审计的文本提取和无损回封工具。用于文本发现、人名绑定、双行文本编辑、变长重定位、跨版本适配与字节级验证；仅分析时不扩展为完整工具或 GUI 交付。"
---

# 无损文本提取与回封

把任务建模为一条可核验的变换链：

```text
只读源 → 封装/结构解析 → 内存 IR → 文本或 ASM 投影
编辑 → 受验证的 ChangeSet → 重定位/重建 → 验证 → 原子提交
```

**字节保真、提取完整性、语义理解是不同问题，不能相互代证。**
零编辑往返一致不证明正文找全；哈希变化不证明译文正确；静态自检不证明目标程序能载入。

## 使用前强制通读门禁

**未读完不得开始计划。** 每次启用本 skill，先完整读取本 `SKILL.md`、下方五份实施补充、
十四份 `references/details/` 完整规格，以及 `references/PRESERVATION.md`，共 **21 份规范文档**。
这一步先于任务计划、实现、修改或验证；此时仅允许为定位和读取这些文件做必要的只读操作。
即使任务只涉及某一章节，也先通读全套，再按任务重点复核，不得只读相关章节或 GUI 摘要。

逐份读到文件末尾，包含代码块、界面布局、表格、验收和交叉引用；
工具返回截断/`Partial` 时继续读取未返回的部分。
在本轮工作记录中列出 21 份已通读的路径，随后才确定任务范围和计划。
不以目录、摘要、搜索命中或脚本的读取结果代替模型阅读，也不凭空声称“已读完”。
若文件缺失、不可读或上下文不足，就分段继续；仍无法完成时暂停计划并说明缺口。
续接任务仅在当前上下文确实保留全部通读记录时复用；丢失记录则重读。

## 先确定范围

沿用用户给定的样本、引擎、语言、版本和已有项目；先读现有分析、实现与 checkpoint。
只执行用户要求的阶段，不把“看看格式”扩展成完整逆向，不强迫所有任务交付 GUI。
已授权的提取/回封流程可连续完成；遇到真实歧义、缺证据或破坏性替换才停下说明。

| 请求 | 本轮完成标准 | 通读后重点复核 |
|---|---|---|
| 分析格式、定位文本、适配变体 | 证据、边界、未决项及允许能力 | [解析与证据](references/parsing-evidence.md) |
| 导出/导入文本、人名或 ASM | 来源明确的投影、稳定身份、严格导入 | [编辑面协议](references/projections.md) |
| 等长/变长回封、布局重排 | 变更生效、引用正确、未编辑对象保留 | [重建与事务](references/rebuilding.md) |
| 验证、排错、交付验收 | 对适用检查提供真实执行证据 | [验证协议](references/validation.md) |
| 交付工具、GUI、批处理提速 | 可复现使用方式、限制与实测结果 | [交付与性能](references/delivery-performance.md) |

本包提供规范、引擎参考页和可复用的标准库解析/回封模块；每个模块仍按本次输入的版本、方言和证据门禁使用，不能把目录登记当成任意游戏的通用承诺。

## 引擎参考与实现目录

`engines/` 是按引擎和格式组织的技术资料树。顶层 95 页对应 `catalog/engines.json` 的引擎条目，`catalog/engine-pages.json` 绑定每页使用的 Python 文件与公开符号；归档、脚本语义和公共编码模块分别位于 `python/archives/`、`python/engines/` 与 `python/common/`。页面下的专项子页记录过滤器、压缩、字体、版本和工作流，不得跳过后直接套用主页规则。

每次处理引擎输入时：

1. 先读对应主页面及其链接的专项子页，确认容器、脚本层、编码和方言。
2. 按页面列出的入口调用模块；先探测并建立来源/哈希，再导出 `gt_input` 和 manifest。
3. 回填前只接受同一 manifest 的 `gt_output`，重解析变更并逐项验证非文本结构。
4. 页面没有声明的版本、密钥、opcode 或 writer 一律保留为 `not_verified`，不得用相似扩展名或字符串扫描代替证据。

公共交换和部署约束见 [roundtrip-contract](guides/roundtrip-contract.md)、[detection](guides/detection.md) 和 [validation-and-deployment](guides/validation-and-deployment.md)；来源与许可证见 [provenance/NOTICE.md](provenance/NOTICE.md)。

## 完整规格必读路由（不是摘要替代）

上表五份参考是实施补充，不能代替原版的具体布局、代码和验收条款。
启用时必须先通读下面的全部完整规格，开始相应工作时再重点复核，不能只读摘要后自行重新设计。
完整章节、全部代码/图示、校订理由见 [内容保全清单](references/PRESERVATION.md)。

| 工作 | 必须读取的完整规格 |
|---|---|
| 范围与完整交付 | [目标/铁律](references/details/principles.md)、[§0 输出与交付清单](references/details/output-sanity-delivery.md)、[§10 报告](references/details/reporting.md) |
| 解析与方言适配 | [§1 VM/证据](references/details/vm-evidence.md)、[§2 IR](references/details/ir-layout.md)、[§3 引用](references/details/reference-joins.md)、[§7 方言](references/details/dialect.md) |
| 文本、人名、ASM 编辑 | [§4 文本协议](references/details/text-protocol.md)、[§5 ASM](references/details/asm.md)、[§2 双编辑面](references/details/ir-layout.md) |
| 重建及验收 | [§6 回封](references/details/repack.md)、[§8 门禁](references/details/gates.md)、[§9 完整验收](references/details/verification.md)，另读当前 CLI/schema |
| GUI/完整工具 | **[§11 完整 GUI 样式与交互](references/details/gui.md)**：保留布局图、路径联动、勾选项、预览、详情与全部验收分组 |
| 性能 | [§12 完整实现建议和代码](references/details/performance.md)，另读性能补充的适用边界 |

**完整工具的默认交付仍是原来的四个 Python 文件、两份文档和两按钮 GUI。**
不得以“优化/精简”为由删除样式、代码、入口或把必需功能改为可选；既有项目不同布局可做职责映射，
但不省交付能力。仅用户明确要求分析、提取或 CLI 等局部工作时，才不扩展到整套工具。
主入口的简短不代表总规格被缩减；示例有技术错误则原位修订并留 before/after，不直接删除。

## 不可破坏的约束

1. **源文件只读。** 记录 SHA-256；修改写到独立输出，验证通过后再提交，不覆盖源。
2. **身份不混淆。** 原始字节是保真依据；IR 是本次解析的结构模型；证据台账说明推断依据。
   外部文本里的 tag、policy、偏移和版本不能自行提升 IR 授予的编辑权限。
3. **按对象和引用站点改写，不按数值全局替换。** 候选扫描可帮助提出假设，但不可直接授权提取或改写。
4. **未知内容保留且不冒充理解。** 明示未解析区、歧义与无法证明的能力；禁止静默替换编码错误或任选候选。
5. **同一编辑对象有唯一决议。** 两个编辑面相同改动合并，不同改动报冲突；不采用“最后写入获胜”。
6. **检查失败不能变成成功。** `not_verified` 与 `fail` 分开；缺输入、跳过必要检查、运行器异常都不能计为通过。
7. **失败不污染成功产物。** 临时文件和正式输出分离；取消/异常保留源、已验证输出和复现记录。

## 执行顺序

### 1. 建立基线与证据

- 清点源文件、源身份/哈希、编码候选、封装层、目标文本类别及已知对照。
- 对整个约定语料枚举结构形态；“整个”由样本清单定义，不以扫描成功的文件反推清单。
- 已知格式优先复用解析器；需要证明 VM 操作时才追踪宿主，不要求所有资源文件先完成 VM 逆向。
- 竞争假设保留证据与反例；多个形态同时匹配是歧义，不能靠声明顺序静默选一个。

### 2. 声明实际理解与能力

| 等级 | 已证明的范围 | 不能仅凭此宣称 |
|---|---|---|
| T0 | 区间边界及原始字节可保留 | 结构或文本语义 |
| T1 | 单元边界/字节序 | 指令边界 |
| T2 | 锚点、字段/文本结构及引用关系 | 完整指令流 |
| T3 | 完整指令边界 | 控制流语义 |
| T4 | 目标、基本块、控制流与必要语义 | 运行时行为等价 |

T0 也可以通过零编辑字节保真。能力取决于**本次操作的影响闭包及独立证据**，
不能把文件中无关的未知区当作一切操作的否决项，也不能凭一个高等级区域放行全文件重排。
等长更新需证明槽容量；变长需证明所有受影响引用与长度依赖；指令编辑另需对应语义证据。

### 3. 导出、校验和重建

- 文本从已解析结构或已证明引用取得；内联文本无需伪造跨文件引用。
- 内存 IR 默认不持久化。只导出请求的工作面；命令行门禁需要 IR 时生成有源哈希的临时验证快照。
- 原文行是只读校验锚，译文预填原文；冻结、编码、占位符、分片集合与源绑定逐项校验。
- ASM diff 只定位变化；以稳定对象 ID 和受限语法解析成 ChangeSet，不把行差异当成语义解析器。
- `probe` 声明适用策略和缺证据原因；`run` 失败后不得无提示换策略掩盖故障。
- 变长是主要用例，但不是对未知格式的无条件承诺；不能支持时给明确能力边界，不输出疑似损坏文件。

### 4. 验证并交付

至少验证本次操作适用的项目：

- 原件哈希保持；本轮实现或交付回封器时，零编辑重建须逐字节一致。
  仅提取任务不要求额外实现重建器；未执行的回封验证明确列为不在本轮范围。
- 有编辑时重解析目标值，检查未编辑对象和受影响引用；**不要求总文件长度变化**。
- 输出合理性与形态统计对照已知语料；偏斜/密度是线索，不是普适正确性定理。
- 实际导出的投影可复现；未导出的 ASM 不凭空要求两份文件。
- 样本支持跨来源验证时执行；缺第二来源就明确报告“未验证跨样本泛化”。
- 只有实际运行过宿主/游戏加载测试才报告“可载入”；否则写清未执行。

验证脚本的输入、证明边界、退出码和组合方法以 [验证协议](references/validation.md) 为准。
输出 `status=pass|fail|not_verified`，对应退出码 `0|1|2`；
聚合器只证明计划内检查的结果，不替代解析器的语义测试。

## 交付选择与状态报告

- 仅分析：证据台账、能力边界、复现命令；不生成无用途的工具骨架。
- 完整工具：默认交付 opcodelist.py、disassembler.py、assembler.py、run_gui.py、
  vm_analysis.md 和 README.md；三种入口及职责按完整规格保留。
- GUI：按 §11 的具体样式生成，不把“同一核心”误解成可以省略界面或自行删减布局；不另写解析器。
- 使用说明面向实际使用者，列真实命令、错误处置、已验证范围和限制。
- 报告分开列 `byte_coverage`、`roundtrip_identity`、理解等级、提取统计、运行时验证；
  附命令/输入/输出路径、哈希、失败或未验证项。完成请求范围即可，不以扩展任务掩盖未完成项。

维护本 skill 时运行 `python -B -m unittest discover -s tests -v`；
增加门禁规则应同时增加会失败的反例和应通过的邻近正例，不能只测试自己的正常输出。

## 统一引擎目录与交换规范

本 skill 将归档/引擎分层、候选检测、JSON 交换、profile 和阶段能力纳入同一套 21 份规范与门禁。需要使用这些能力时，再读 [统一适配架构](references/compatibility-architecture.md)、[IR 规则](references/ir.md)、[检测规则](references/detection.md)、[JSON 投影](references/json-projection.md) 和 [来源台账](references/licensing.md)。

- `catalog/engines.json` 收录 95 个引擎与格式族条目；它是 profile seed，不是 95 个已验证 writer。
- `python/core/`、`python/projections/` 和 `python/detectors/` 提供与引擎无关的 IR、标准 JSON 交换和候选检测；`python/archives/`、`python/engines/` 和 `python/common/` 提供页面对应的参考 parser/writer 与公共编码实现。
- `extract`、`repack`、`runtime` 分别记录；检测器不能直接选择 writer。manifest、locator、源哈希和 ChangeSet 是 JSON/ASM 与回封之间的唯一连接。
- 每个适配器必须同时补 provenance、拒绝路径、零编辑往返、变长回填和对应 catalog 状态；未验证项写 `not_verified`。

## 引擎索引

<!-- ENGINE_INDEX_START -->
| 引擎/格式族 | 页面 |
|---|---|
| AdvSys3 / arc*.dat | [advsys3](engines/advsys3.md) |
| AGSI / SB2 | [agsi](engines/agsi.md) |
| Ail / SNL | [ail](engines/ail.md) |
| ANIM：滚动密钥 DAT / SCE 局部参考 | [anim](engines/anim.md) |
| ArcGameEngine：AGE 字符串池算法 | [arcgameengine](engines/arcgameengine.md) |
| ARCX 工具目录 / SCX.ARC 顺序记录 | [arcx](engines/arcx.md) |
| Artemis Engine：AST 文本剧本（`.ast`） | [artemis-ast](engines/artemis-ast.md) |
| Artemis Engine：SCP 文本剧本（`.txt` / `.iet`）与 pf8 多分卷 | [artemis-scp](engines/artemis-scp.md) |
| Artemis：ASB 项目树的保真读写 | [artemis](engines/artemis.md) |
| AST / ARC1、ARC2 | [ast](engines/ast.md) |
| AZSystem：ASB 包装与解密后命令 | [azsystem](engines/azsystem.md) |
| BGI / Ethornell：有界索引、DSC 编解码与标准 V1 往返 | [bgi](engines/bgi.md) |
| BlackRainbow：分段脚本与文本 XOR | [blackrainbow](engines/blackrainbow.md) |
| BlueGale：BDT 与 indexwww.dat 联动 | [bluegale](engines/bluegale.md) |
| CatSystem2：KIF/INT、CST 对话与安全提取 | [catsystem2](engines/catsystem2.md) |
| Circus：按游戏配置解释 MES token | [circus](engines/circus.md) |
| CScript：已解压剧本中的有界记录 | [cscript](engines/cscript.md) |
| Cyberworks：a0 的 S/T 长度块 | [cyberworks](engines/cyberworks.md) |
| DigitalWorks / BunBun TAK | [digitalworks](engines/digitalworks.md) |
| EAGLS / ALIS：SCPACK、文本尾加密与标签修复 | [eagls](engines/eagls.md) |
| EmonEngine / EME | [emonengine](engines/emonengine.md) |
| Entis GLS：SRCXML 多语言消息与选择属性 | [entis-gls](engines/entis-gls.md) |
| Escu:de：ESC-ARC2、分离消息文件与 ESCR1_00 | [escude](engines/escude.md) |
| ExHibit：RLD v3 静态解密、文本提取与回注 | [exhibit](engines/exhibit.md) |
| Favorite：HCB u8 字符串长度与绝对地址更新 | [favorite](engines/favorite.md) |
| FlyingShine / PD2 | [flyingshine](engines/flyingshine.md) |
| FrontWing / FRONTWING_ADV CSB | [frontwing](engines/frontwing.md) |
| GSD：先 decode 的 v2 族 SPT 与 global.dat | [gsd](engines/gsd.md) |
| GxEngine：V3 MWB 字符串与 zlib 包装 | [gxengine](engines/gxengine.md) |
| HCSystem / PACK | [hcsystem](engines/hcsystem.md) |
| Hexenhaus：NORI 的 XOR53 固定槽 | [hexenhaus](engines/hexenhaus.md) |
| HotSoup / HSP DPMX | [hotsoup](engines/hotsoup.md) |
| ICE / 索引字表文本流 | [ice](engines/ice.md) |
| IKURA / MPX、ISF | [ikura](engines/ikura.md) |
| Ivory / fAGS OCB | [ivory](engines/ivory.md) |
| Kaguya：message.dat 与 LINK6 | [kaguya](engines/kaguya.md) |
| Kirikiri / KAG：剧本提取、回填与 XP3 补丁 | [kirikiri](engines/kirikiri.md) |
| Leaf / KCAP、SDT | [leaf](engines/leaf.md) |
| Livemaker：外部导出的 Original text CSV 方言 | [livemaker](engines/livemaker.md) |
| Majiro：MJO 异或与文本 / Ruby 指令片段 | [majiro](engines/majiro.md) |
| Malie / 2008 UTF16 与 data5 EXEC | [malie](engines/malie.md) |
| Masys / MEG 表达式字符串 | [masys](engines/masys.md) |
| MED / MDN0：有界脚本归档与序号引用回写 | [med](engines/med.md) |
| Melonpan / WCW TTD | [melonpan](engines/melonpan.md) |
| Mirai / ACV1 script.dat | [mirai](engines/mirai.md) |
| M no Violet / DAT、CScript | [mnoviolet](engines/mnoviolet.md) |
| MoonHir：FPK → FBX → 第一文本区块 | [moonhir](engines/moonhir.md) |
| Musica：SC 消息、选择与文本转义 | [musica](engines/musica.md) |
| Mware：Squirrel literal 与引用级克隆 | [mware](engines/mware.md) |
| NEJII / CDT、144字节BIN | [nejii](engines/nejii.md) |
| NekoSDK：ADVSCRIPT2 显示与日志记录 | [nekosdk](engines/nekosdk.md) |
| NeXAS：PAC 尾索引与 BIN 字符串池回填 | [nexas](engines/nexas.md) |
| NonColor / legacy ACV | [noncolor](engines/noncolor.md) |
| NScripter：容器可回写，文本仍须词法与命令边界审核 | [nscripter](engines/nscripter.md) |
| NSystem：BIN 预设的地址表和独立消息记录 | [nsystem](engines/nsystem.md) |
| Overflow：TextRes / Log XML 方言 | [overflow](engines/overflow.md) |
| Patisserie：OZ / OFST 归档 | [patisserie](engines/patisserie.md) |
| Propeller：MSC 长度文本与样式 toggle | [propeller](engines/propeller.md) |
| PureMail：OBJ V1 / V2 索引文本池 | [puremail](engines/puremail.md) |
| QLIE：PACK 3.0 解包、ImoScripter 对白与模板重封包 | [qlie](engines/qlie.md) |
| Ransel：BCD / BCL 配对归档 | [ransel](engines/ransel.md) |
| RealLive：文本 token 与换行指令片段 | [reallive](engines/reallive.md) |
| Ren’Py：RPA/ARC3 归档与 RPYC2 编译脚本回填 | [renpy](engines/renpy.md) |
| RPG Maker：MV JSON 与 VX Marshal 转换中间态 | [rpgmaker](engines/rpgmaker.md) |
| SakanaGL：SX 密码与已解码索引 | [sakanagl](engines/sakanagl.md) |
| ScenePlayer：PMX 剧本归档 | [sceneplayer](engines/sceneplayer.md) |
| ScrPlayer：XOR 字符串表与命令指针 | [scrplayer](engines/scrplayer.md) |
| SFA：FGA Huffman 成员与 AOS 文本线索 | [sfa](engines/sfa.md) |
| ShSystem：只导出特定 scriptcall 0x33 | [shsystem](engines/shsystem.md) |
| Siglus：Scene.pck 解包不等于 `.ss` 文本往返 | [siglus](engines/siglus.md) |
| Silky / Silkys：MAP 全索引与 UTF-16 指针修复 | [silky](engines/silky.md) |
| SLGSystem：SZS100__ 容器与两种密码模式 | [slgsystem](engines/slgsystem.md) |
| Softpal：PAC 解包与 Sv20 / TEXT.DAT / POINT.DAT | [softpal](engines/softpal.md) |
| StudioMiris：SKMSd 消息资源表 | [studiomiris](engines/studiomiris.md) |
| StudioPolaris：已解密 SCD_ 字节码 | [studiopolaris](engines/studiopolaris.md) |
| Succubus：RIFF / VFA1 事件式归档 | [succubus](engines/succubus.md) |
| SYSTEM-ε：BIN 文本段与候选跳转模式 | [system-epsilon](engines/system-epsilon.md) |
| SystemC / SystemB3：FPK、ACT 与 UTF-8 TXD/PTR | [systemc](engines/systemc.md) |
| SystemNNN：开发版定长槽与发布版 word 地址 | [systemnnn](engines/systemnnn.md) |
| Tanaka：SCB1 模板重封与 BIN 文本记录 | [tanaka](engines/tanaka.md) |
| TmrHiro：text 流的 i16 长度往返 | [tmrhiro](engines/tmrhiro.md) |
| Triangle：MOP / EXD / KLH 的独立文本块 | [triangle](engines/triangle.md) |
| U-GOS：.o 指针引用的字符串块 | [ugos](engines/ugos.md) |
| U-MeSoft：PK 尾索引与 SCR/TBL literal 封装 | [umesoft](engines/umesoft.md) |
| Unison / Softpal Lazy：VAL 分离式字符串池 | [unison](engines/unison.md) |
| Unity：Utage 剧情表与 serialized asset 回写 | [unity](engines/unity.md) |
| Violent BIN 规则：只读 JIS 候选证据 | [violent](engines/violent.md) |
| Whale：文本行结构、SELECT 与 [n] | [whale](engines/whale.md) |
| WillPlus / AdvHD：ARC/AR2 解包与 WS2 v1 代码子集 | [willplus](engines/willplus.md) |
| Winters：IFP 无遮罩子集与 ISD 尺寸条件 | [winters](engines/winters.md) |
| Xuse：GD + DLL 数据索引与脚本 XOR | [xuse](engines/xuse.md) |
| Yaneurao：Itufuru 长度字符串指令 | [yaneurao](engines/yaneurao.md) |
| Yatagarasu：PKG v1 密钥索引归档 | [yatagarasu](engines/yatagarasu.md) |
| Yuka：YKS002 类型化文本池 | [yuka](engines/yuka.md) |
| YU-RIS：YPF 解包、YBN 分区 XOR 与 ysc.ybn | [yuris](engines/yuris.md) |
<!-- ENGINE_INDEX_END -->
