# lossless-text-repack

做游戏脚本翻译：把文本提出来，翻译后再装回去。
这里同时包含通用规范、按引擎组织的格式资料、标准库解析/回封模块和可复现测试；新版本或新方言仍需按证据门禁单独确认。

## 安装

把当前 `lossless-text-repack` 文件夹放到技能目录，重新加载客户端即可。安装目录第一层必须直接包含 `SKILL.md`。

| 客户端 | 目录 |
|---|---|
| Codex | `~/.codex/skills/` |
| Claude Code | `~/.claude/skills/` |
| 其他 | 按客户端的技能目录配置 |

macOS / Linux，以 Codex 为例：

```bash
mkdir -p ~/.codex/skills
cp -R lossless-text-repack ~/.codex/skills/lossless-text-repack
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$HOME\.codex\skills" | Out-Null
Copy-Item -LiteralPath ".\lossless-text-repack" -Destination "$HOME\.codex\skills\lossless-text-repack" -Recurse
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
references/*.md       实施补充、适配架构、投影、检测和内容保全清单
scripts/              7 个检查脚本和 run_gates.py
tests/                通用门禁与引擎回归测试
agents/               客户端显示信息
engines/              95 个顶层引擎页、专项子页和格式参考
guides/               提取、回填、编码、检测和部署工作流
catalog/              能力注册表、逐页实现索引和格式 catalog
provenance/           来源、许可证、哈希和改编记录
tools/                引擎索引与独立完整性检查
assets/               明确记录的可选资源
profiles/             profile schema 与模板
python/               IR、投影、候选检测、归档和引擎实现
```

完整工具仍按规范交付 `opcodelist.py`、`disassembler.py`、`assembler.py`、
`run_gui.py`、`vm_analysis.md` 和使用说明；GUI 是两按钮界面。
章节去向及逐项修订见 [内容保全清单](references/PRESERVATION.md)。

## 统一引擎目录与交换规范

本 skill 将引擎表、归档/引擎分层、候选探测、manifest/locator 和阶段能力统一接入原有 IR 与回封门禁。原有 `SKILL.md`、21 份规范、检查脚本和回归测试继续作为总规范。

统一入口：

- [统一适配架构](references/compatibility-architecture.md)：ArchiveAdapter、EngineAdapter、Dialect/Profile 和能力状态；
- [统一 IR 规则](references/ir.md)：entry、locator、manifest、ChangeSet 的互操作字段；
- [JSON 投影](references/json-projection.md)：`text_input`/`text_output`、姓名策略和 sidecar；
- [候选检测](references/detection.md)：弱信号、竞争假设和 resolver 门禁；
- [95 个引擎 catalog](catalog/engines.json)：能力状态和升级门禁；
- [逐页实现索引](catalog/engine-pages.json)：每个引擎页面对应的模块和公开符号；
- `engines/`、`guides/`：结构、编码、压缩、回填和限制的完整资料；
- `python/archives/`、`python/engines/`、`python/common/`：按页面选择的标准库实现；
- `python/core/`、`python/projections/`、`python/detectors/`：通用 IR、投影和候选检测契约；
- `scripts/check_skill_integrity.py`：检查 skill 完整性、schema、链接和 Python 语法。

引擎页面和模块已经随包提供，但“目录登记”仍不等于任意游戏版本的支持。只有当前输入满足页面的结构条件，并且 parser/writer、合成反例、零编辑往返、变长重解析和实际样本证据齐全时，才把对应阶段从 `catalog-only` 升级为 `verified`。

## 许可

根目录原有文件遵循 MIT；移植模块按文件 SPDX 标识及 `provenance/licenses/` 中的对应许可证执行，完整范围见 [provenance/NOTICE.md](provenance/NOTICE.md)。
