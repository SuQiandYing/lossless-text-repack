# lossless-text-repack

把游戏脚本里的文本提取出来翻译，改完再装回去，而且能证明只有你改的地方变了。

这是给 AI 编程助手用的技能包。装上以后，你让它帮你逆向某个脚本格式做本地化，它会按这份规范来做——而不是随手写个正则抓字符串然后祈祷装回去还能跑。

## 它解决的问题

自己写解包工具做翻译，最麻烦的不是写不出来，而是写出来了、测试全过了、结果是错的。

真实案例：一份工具在 264 个文件上跑到字节覆盖率 100%、不修改时重建出来的文件和原件逐字节相同、158 项测试全绿。换到同引擎另一部作品，提取出 418 条文本——414 条人名、4 条 UI、**台词 0 条**。没有报错，没有告警。

原因是那部作品把台词塞在多语言嵌套结构里（`texts[i][1][0][1]`），工具只读平铺的那个槽位，而那个槽位的值是 `null`。

问题在于，常规的检查手段一个都拦不住这种情况：

- 字节覆盖率 100%：字节归属跟看懂内容是两件事
- 重建后逐字节一致：**你什么都没提取出来的时候，这项最容易通过**
- 测试全绿：测试用的语料和开发时用的是同一批，共享同一个盲区

所以这份规范除了字节层面的检查，还强制检查**产出本身合不合理**：含对话的剧本抽出 0 条台词，就是失败，不许拿"这个样本就这样"当解释。

另外几个坑，规范里都写了怎么绕：

**改引用要按位置改，不能按值改。** 变长回封时文本位置会变，所有指向它的地方都要更新。如果你的做法是"扫一遍文件，把所有等于旧偏移的数值换成新偏移"，那你会连带改掉恰好数值相同的常量、坐标、标志位、别的表的容量——文件还能加载，但行为已经乱了。这种损坏哈希查不出来（编辑过的文件本来就该变），长度检查也查不出来（长度没变）。

**改完之后哈希没变，说明你的编辑丢了。** 很多人拿"重建结果和原件哈希一致"当成功标志，这在零编辑时是对的，一旦真改了内容就完全反了。

**译文变长必须支持。** 日译中偏短、日译英显著偏长，只支持等长覆写的工具遇到第一条超长文本就卡住，而且没法靠改措辞绕过去——专有名词、数字、标点都可能让长度上升。

**没有兜底分支。** 结构形态匹配不上就报错，不许返回空列表——上面那次事故就是"平铺分支成功匹配了一个全是 null 的结构"。编码解不出来不许静默替换，歧义不许随便挑一个，策略失败不许自动降级去试下一个。

## 用法

装好之后不用记命令，直接说你要干什么：

> 帮我逆向 `D:\Game\scn` 下的脚本，把台词提取成可翻译的文本

> 这些译文改完了，装回去，检查一下有没有改坏别的地方

> 我已经有一个解包脚本，但感觉漏抽了内容，帮我查一下

它会按规范先摸清格式、申报自己看懂了多少（分 T0-T4 五级，看懂多少算多少，不许虚报）、产出两种可编辑的文件：

- `texts/` 下的双行文本，一行原文一行译文，给翻译的人用
- `asm/` 下的反汇编清单，要改逻辑才需要

翻译只改译文那行。装回去的时候会核对原文行有没有被动过——这一条能同时抓住错位、误改、用旧文件覆盖、以及编辑器偷偷把半角引号换成全角这类问题。

配套还有一个两按钮的图形界面（输出文本 / 回封文本），给不懂逆向的人用，拖个文件夹进去就能跑。

## 7 个检查脚本可以单独用

如果你已经有自己的工具，不想按这套规范重写，可以只拿这些脚本接到你的 CI 里。它们只读文件、输出 JSON、退出码 0 或 1，不依赖技能本体也不依赖第三方库：

```bash
# 抽出来的东西合不合理：台词是不是 0 条？是不是 95% 都是同一类？
python scripts/check_output_sanity.py reports/extract_report.json

# 结构变体查全了没：有没有没见过的形态？声明了却从来没命中的形态？
python scripts/check_shapes.py reports/shapes.json --corpus-wide

# 没改时哈希必须一样，改了时哈希必须不一样（两个方向相反，都要测）
python scripts/check_determinism.py edit SAMPLE rebuilt/SAMPLE --no-edit
python scripts/check_determinism.py edit SAMPLE rebuilt/SAMPLE --edited

# 变长回封是按位置改的还是按值改的（后者会改坏同值常量）
python scripts/check_sites.py orig.bin rebuilt.bin ir/join_sites.jsonl

# 译文文件有没有被改坏（13 项：改了原文行、编号乱了、占位符破了、超长……）
python scripts/check_dsat.py ir/ texts/

# 字节区间有没有缺口、重叠、哈希不符
python scripts/coverage_certificate.py SAMPLE reports/coverage_certificate.json

# 引擎相关的魔数、opcode 表、正则有没有混进通用代码里（AST 分析，不是文本匹配）
python scripts/check_no_literals.py src/ --exclude opcodelist
```

需要 Python 3.11+，只用标准库。每个都能 `--help`。

## 安装

技能就是一个装着 `SKILL.md` 的文件夹，放到客户端会扫的地方就行：

```
<客户端配置目录>/skills/<技能名>/SKILL.md
```

### 1. 下载

```bash
git clone https://github.com/<你的用户名>/lossless-text-repack.git
```

或者在 GitHub 页面点 **Code → Download ZIP** 然后解压。

### 2. 放进技能目录

| 客户端 | 所有项目可用 | 只给当前项目用 |
|---|---|---|
| Claude Code / Claude 桌面版 | `~/.claude/skills/` | `<项目>/.claude/skills/` |
| Codex CLI | `~/.codex/skills/` | — |
| 其他客户端 | `~/<配置目录>/skills/` | `<项目>/<配置目录>/skills/` |

各家的配置目录名不一样（`.claude`、`.codex`……），但里面 `skills/<技能名>/SKILL.md` 这层结构是一致的。表里没有你的客户端，就去家目录找那个以点开头的同名文件夹，在里面建 `skills/`。

Windows 上 `~` 就是 `C:\Users\你的用户名`。

**Linux / macOS / Git Bash：**

```bash
mkdir -p ~/.claude/skills
cp -r lossless-text-repack ~/.claude/skills/
```

**Windows PowerShell：**

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills"
Copy-Item -Recurse lossless-text-repack "$HOME\.claude\skills\"
```

装完是这样，`SKILL.md` 必须在第一层：

```
~/.claude/skills/
└── lossless-text-repack/
    ├── SKILL.md          ← 就在这一层，不能再套一层文件夹
    ├── references/
    └── scripts/
```

想装到多个客户端，就往每个目录各复制一份，互不影响。

### 3. 重启客户端

技能列表是启动时扫的，**不重启看不到**。

验证：

```bash
ls ~/.claude/skills/lossless-text-repack/SKILL.md
python ~/.claude/skills/lossless-text-repack/scripts/check_no_literals.py --help
```

然后输入 `/lossless-text-repack` 试试，或者直接说你的需求让它自己判断要不要用。

### 装不上的几种情况

| 现象 | 怎么回事 |
|---|---|
| 客户端找不到 | 多套了一层目录。应该是 `skills/lossless-text-repack/SKILL.md`，不是 `skills/lossless-text-repack/lossless-text-repack/SKILL.md`——解压 ZIP 很容易变成后者 |
| 装了没反应 | 没重启 |
| 脚本报语法错误 | Python 低于 3.11，脚本用了 `X \| Y` 这种类型写法 |
| 中文输出乱码 | 控制台代码页不是 UTF-8。脚本写出的 JSON 文件本身没问题，加 `--report 文件名` 输出到文件再看 |

不想用 git 的话，手动建个 `lossless-text-repack` 文件夹，把 `SKILL.md`、`references/`、`scripts/`、`agents/` 复制进去，一样能用。纯文本，没有任何构建步骤。

## 里面有什么

```
SKILL.md              主规范，§0-§10
references/
  gui.md              图形界面怎么做（要做界面时才读）
  performance.md      纯 Python 怎么跑快（批量慢了才读）
scripts/              7 个检查脚本
agents/skill.yaml     界面元数据，部分客户端会读
```

`references/` 里那两块单独放，是因为它们只在特定阶段有用，不该每次都占着上下文。

## 三条硬指标

规范里最不能混的是这三个，它们各管一件事：

```
byte_coverage       每个字节都有唯一归属      恒为 100%，不可协商
roundtrip_identity  不改时重建结果逐字节相同  必须通过，不可协商
decode_tier         看懂了多少（T0-T4）      按证据申报，决定你能干什么
```

前两个是死线。第三个是诚实度：只看懂"这是 4 字节一组的数据流"（T1）加上能原样重建，就已经是合格交付了；能力不够却申报 T3 才是问题。想做变长回封至少要 T2（引用位置全部定位），想重排结构要 T3（跳转和表容量都算得清）。

完整规范见 [SKILL.md](SKILL.md)。

## 改这个仓库

规范和脚本要一起改：写进规范的规则，只要能机械检查，就不该只留在文档里。

加或改检查脚本时，两个方向的对照用例都要有——一份已知有问题的输入（必须报出来）和一份已知没问题的输入（必须不报）。只测一个方向的话，判断写反了都发现不了。

## 许可

MIT
