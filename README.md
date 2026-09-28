# lossless-text-repack

做游戏脚本翻译：把文本提出来，翻译后再装回去。
这里是制作工具时用的规范和检查脚本；新游戏的文件格式仍需单独适配。

## 安装

把整个 `lossless-text-repack` 文件夹放到技能目录，重新加载客户端即可。

| 客户端 | 目录 |
|---|---|
| Codex | `~/.codex/skills/` |
| Claude Code | `~/.claude/skills/` |
| 其他 | 按客户端的技能目录配置 |

macOS / Linux，以 Codex 为例：

```bash
mkdir -p ~/.codex/skills
cp -R lossless-text-repack ~/.codex/skills/
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -LiteralPath ".\lossless-text-repack" -Destination "$HOME\.codex\skills\" -Recurse
```

已有同名目录先备份。确认 `SKILL.md` 在 `lossless-text-repack/` 第一层，不要多套一层文件夹。
使用前先读完 `SKILL.md`、14 份完整章节、5 份补充文档和保全清单，共 21 份规范文档；读完再计划。

## 检查脚本

需要 Python 3.11+，只用标准库。七个检查脚本可单独运行，`run_gates.py` 用来汇总本次要跑的检查。

```bash
python scripts/check_output_sanity.py reports/extract.json            # 提取数量和类别
python scripts/check_shapes.py reports/shapes.json                    # 已观测的结构形态
python scripts/check_determinism.py edit source.bin rebuilt.bin --no-edit  # 零编辑逐字节一致
python scripts/check_sites.py source.bin rebuilt.bin validation/join_sites.jsonl  # 等长改写站点
python scripts/check_dsat.py validation/ir texts/                     # 双行文本导入
python scripts/coverage_certificate.py source.bin reports/cert.json  # 字节区间覆盖
python scripts/check_no_literals.py implementation/ --exclude opcodelist  # 方言常量是否混入通用代码
python scripts/run_gates.py validation/gates.json                     # 按计划汇总
```

结果是 JSON；退出码 `0` 为通过，`1` 为失败，`2` 为证据不足、未验证。
这些命令只检查各自收到的证据，不会替你解析游戏文件。
完整输入格式、目标编码绑定、变长布局映射和聚合计划见 [验证协议](references/validation.md)。
改动脚本后运行：

```bash
python -B -m unittest discover -s tests -v
```

## 文件

```text
SKILL.md              入口和使用规则
references/details/   原规范的 14 个完整章节，含 GUI 布局与代码示例
references/*.md       5 份实施补充及内容保全清单
scripts/              7 个检查脚本和 run_gates.py
tests/                回归测试与原文对照
agents/               客户端显示信息
```

完整工具仍按规范交付 `opcodelist.py`、`disassembler.py`、`assembler.py`、
`run_gui.py`、`vm_analysis.md` 和使用说明；GUI 是两按钮界面。
章节去向及逐项修订见 [内容保全清单](references/PRESERVATION.md)。

## 许可

MIT
