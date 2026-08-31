# lossless-text-repack

给 AI 编程助手用的技能包。做游戏脚本翻译：把文本提出来翻译，改完装回去。

## 作用

想翻译一款游戏，脚本是私有格式，网上没有现成工具。装上这个技能，跟 AI 说：

> 帮我逆向 D:\Game\scn 下的脚本，把台词提取成可翻译的文本

它会写出配套的解包和回封工具，然后给你一份这样的文本：

```
○00000001○msg○こんにちは
●00000001●msg●你好
```

`○` 是原文别动，`●` 那行填译文。翻完让 AI 装回去，游戏就是中文的了。

它主要防的是几件事：

- **抽漏**。台词藏在嵌套结构里的时候，工具容易只抽到人名和菜单，正文一条没有，而且不报错。所以规范强制检查：剧本抽出 0 条台词，直接算失败。
- **译文长度**。中文比日文短、英文比日文长，很多工具只支持等长替换，遇到长一点的句子就卡住。这里支持随便变长。
- **改坏别的地方**。文本挪位置后，指向它的引用要更新。粗暴的做法是全文搜索把等于旧位置的数字替换掉，结果会连坐标、血量、道具编号一起改掉——游戏能开，但玩起来到处出问题，而且这种错查不出来。
- **白改**。译文填了但没生效，装回去的文件跟原来一模一样，你以为成了。

翻译之外，还能改脚本逻辑（改分支、改跳转），以及给不懂这些的人用的两按钮界面：输出文本、回封文本。

## 安装

放到客户端的技能目录，重启即可。

| 客户端 | 目录 |
|---|---|
| Claude Code / 桌面版 | `~/.claude/skills/` |
| Codex CLI | `~/.codex/skills/` |
| 其他 | `~/<配置目录>/skills/` |

```bash
git clone https://github.com/<你的用户名>/lossless-text-repack.git
mkdir -p ~/.claude/skills
cp -r lossless-text-repack ~/.claude/skills/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills"
Copy-Item -Recurse lossless-text-repack "$HOME\.claude\skills\"
```

`SKILL.md` 要在 `lossless-text-repack/` 第一层，别多套一层文件夹（解压 ZIP 常出这问题）。装完重启客户端，不重启看不到。

装多个客户端就各复制一份。

## 检查脚本

`scripts/` 下 7 个脚本能单独用，接到自己项目的 CI 里。只读文件、输出 JSON、退出码 0/1，需要 Python 3.11+，只用标准库。

```bash
python scripts/check_output_sanity.py reports/extract_report.json    # 抽出来的合不合理
python scripts/check_shapes.py reports/shapes.json --corpus-wide     # 结构变体查全了没
python scripts/check_determinism.py edit SAMPLE rebuilt/SAMPLE --edited   # 改了哈希必须变
python scripts/check_sites.py orig.bin rebuilt.bin ir/join_sites.jsonl    # 引用是否按位置改
python scripts/check_dsat.py ir/ texts/                              # 译文文件有没有被改坏
python scripts/coverage_certificate.py SAMPLE reports/cert.json      # 字节有没有缺口重叠
python scripts/check_no_literals.py src/ --exclude opcodelist        # 引擎魔数有没有混进通用代码
```

## 文件

```
SKILL.md              规范正文
references/gui.md     界面怎么做
references/performance.md   批量跑快
scripts/              7 个检查脚本
```

完整规范见 [SKILL.md](SKILL.md)。

## 许可

MIT
