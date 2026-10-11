# 引擎、方言和归档

## Profile 最小结构

在 `profiles/<id>.json` 登记：

```json
{
  "schema": "lossless-text-repack.profile/1",
  "id": "example-engine-v1",
  "family": "example-engine",
  "aliases": ["Example"],
  "archive_profiles": ["example-arc-v2"],
  "dialects": [{"id": "v1", "selectors": ["version-field:1"]}],
  "capabilities": {"detect": "candidate-only", "extract": "not_verified", "repack": "not_verified", "runtime": "not_verified"},
  "evidence": [],
  "limitations": [],
  "license": {"implementation": "MIT", "sources": []}
}
```

不要以游戏名新建 profile。游戏差异应成为参数、版本证据、辅助表或独立 dialect；只有结构布局、编码、opcode 或 writer 语义真正不同才拆分 profile。

## 实现步骤

1. 先为容器/脚本写最小探测和拒绝路径，再写完整读取；
2. 建立短头、越界、未知字段、共享引用和编码失败的反例；
3. 让 parse 生成完整 IR 和 evidence，不直接生成 JSON；
4. 通过原文投影/导入验证后再实现 writer；
5. 先做零编辑往返，再做变长中文/控制码/多姓名和包索引变化；
6. 把实际能力更新到 catalog，附测试命令和输入哈希；
7. 有真实宿主试注才升级 runtime 状态。

## 不能做的快捷方式

- 只因文件后缀、可读字符串或上游 `CanWrite` 就启用 writer；
- 复制一个相似引擎的 opcode 表，遇到未知项填零或吞掉；
- 用全局 `bytes.replace` 替换文本或地址；
- 把原文复制到输出目录称作零编辑往返；
- 让用户改 manifest 规避 stale source、缺行或控制码错误；
- 把来源仓库的 GPL/MIT/其他代码统一重新标成 MIT。

## 贡献检查

运行 `python scripts/check_skill.py` 和相关测试。文档链接、profile schema、catalog 计数、Python 语法、源路径安全和 license notice 都必须通过；失败项和未验证项随变更说明保留。
