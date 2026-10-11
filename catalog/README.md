# 引擎目录

`engines.json` 和 `engines.md` 是本 skill 维护的引擎/格式族能力注册表和审阅表。`engine-pages.json` 是逐引擎页面到 Python 模块/公开符号的机器索引；实际技术细节位于根目录 `engines/`，登记条目不等于已经对任意游戏版本完成验证。

每个条目都从以下状态开始：

```text
detect: not_verified
extract: catalog-only
repack: not_verified
runtime: not_verified
```

只有当前目录同时具备本地 profile、方言选择条件、解析/写出实现、合成正反例、零编辑往返、变长重解析和对应证据时，才升级单个阶段。运行时状态还需要真实宿主加载记录。

`engines.json` 只负责能力状态，`engines.md` 是按它生成的审阅表，`engine-pages.json` 负责资料和实现映射。修订条目或页面后运行 `python scripts/check_skill_integrity.py` 与 `python tools/check_skill.py`。
