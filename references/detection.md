# 检测、歧义与能力矩阵

## 候选探测

探测器只读取有界头部、索引和少量结构，不执行资源中的代码，不解压超过预算。输出至少包括：

```json
{
  "path": "data.pak",
  "candidate": "xp3",
  "score": 0.82,
  "signals": ["magic:XP3", "index-in-range"],
  "counter_evidence": ["version-field-unread"],
  "requires": ["explicit-dialect", "index-check"],
  "status": "candidate"
}
```

扩展名、目录名、可读日文和单一字符串只能是弱信号。强信号应是魔数、版本、索引边界、长度/偏移一致性、已知命令布局和辅助表交叉验证。多个 profile 同时满足结构时返回 `ambiguous`，不得按分数微小差异自动写回。

## Resolver 门禁

resolver 要求调用方显式确认：目标成员集合、archive profile、engine profile、dialect、编码、阶段和预算。只有 `detect=confirmed` 且对应 adapter 存在时才进入 parse；只有 `extract=verified` 且 manifest 完整时才导出可编辑投影；只有 `repack=verified` 的 profile 才能写出正式替换成员。`analysis` 结果可以保存证据和报告，但不能生成可部署文件。

## 分阶段矩阵

| 层 | 允许声明 | 不能推断 |
|---|---|---|
| archive | 成员边界、解压/索引往返 | 剧本语义或对白完整性 |
| engine | 指定方言的记录、姓名、正文、控制码 | 所有版本或所有游戏 |
| projection | 行顺序、身份和编辑字段可回收 | writer 能处理未导出字段 |
| repack | 结构重建、重定位和非文本保留 | 宿主会加载 |
| runtime | 实际加载、字体、补丁优先级 | 其他版本仍可用 |

## 报告模板

```text
candidate: ambiguous
archive: confirmed / xp3-v2
engine: confirmed / kirikiri-kag-v2
dialect: explicit / evidence ev-001..ev-007
extract: verified
repack: not_verified (shared cache field unknown)
runtime: not_verified (game not started)
```

这份状态必须和结果目录中的 JSON 报告一致；不能用“函数存在”“页面已登记”替代证据。
