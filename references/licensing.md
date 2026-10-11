# 来源与许可证

## 本目录

本目录中的规范、IR、投影、检测器、目录和测试按根目录 MIT License 发布。运行时不导入外部仓库、不执行包外模块，也不携带游戏资源、私有密钥、二进制或用户翻译。

引擎目录只记录格式事实、别名、能力状态和本地证据入口；它不复制实现代码或大段受版权保护的表达。目录登记本身不能授权 parser 或 writer。

## 参考资料

本 skill 的架构和引擎条目来自公开格式资料、样本观察和本地验证。每个条目都要把资料事实与本地能力分开记录：资料可以说明候选格式，只有当前 adapter 的真实测试才能改变 `extract`、`repack` 或 `runtime` 状态。

若某个实现来自可识别的外部项目，必须在 `provenance/` 添加完整来源记录；未完成记录时只可保留算法事实和格式描述，不得复制代码或宣称已有实现。

## 未来移植记录

从外部资料移植代码前新增一条来源记录：

```text
repository: <url>
commit: <full sha>
path: <relative file>
symbols: <class/function range>
license: <SPDX id>
changes: <porting and safety changes>
tests: <local test ids>
```

保留原版权和许可证文本；混合来源按最严格适用义务分发，不能因为本目录是 MIT 就覆盖受限组件。算法事实、格式魔数和公共接口名称可以在不复制原文的前提下记录，但仍应给出出处和证据范围。
