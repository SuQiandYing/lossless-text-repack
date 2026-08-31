# lossless-text-repack

给 AI 编程助手用的技能包。做游戏脚本翻译：把文本提出来翻译，改完装回去。

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
SKILL.md     规范正文，§0-§12 全在一个文件里
scripts/     7 个检查脚本
```

完整规范见 [SKILL.md](SKILL.md)。

## 许可

MIT
