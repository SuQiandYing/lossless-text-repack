# 归档、引擎适配器与回封

## 工作目录

```text
result/
  original/       # 选择的源成员和辅助表，带哈希
  extracted/      # 解析中间物，不作为输入再扫描
  text_input/
  text_output/
  rebuilt/        # 临时构建物
  reports/
```

每次运行生成唯一结果目录，扫描器排除所有结果目录。任何正式写出先落到临时文件，完成重解析和校验后原子替换到 `rebuilt/`。源输入、原始成员和旧成功输出不覆盖。

## 回封顺序

1. 重新读取原始成员并核对源哈希；
2. 读取 projection + manifest，构建 ChangeSet；
3. 以原 engine/dialect parse，校验 entry、locator、控制码和编码；
4. 计算影响闭包，更新文本、长度、字符串池、引用、跳转、对齐和校验；
5. 以相同 archive profile 重建成员和外层索引；
6. 对输出再次 parse，比较译文、未编辑 entry、opaque spans 和元数据；
7. 记录 `pass/fail/not_verified`，只有计划内检查全部通过才提交正式输出。

零编辑重建是最强的保真回归，但不要求总文件长度不变。若压缩器不保证字节相同，应分别报告“语义/结构往返通过”和“字节身份未通过”，不能合并成一个成功标记。

## 失败处理

- `source_changed`：停止，不重写 manifest 或猜测新源；
- `ambiguous_dialect`：保存候选和反例，要求显式 profile；
- `unknown_opcode`/`unknown_reference`：保留 raw，禁止继续写出该影响闭包；
- `encoding_unrepresentable`：要求字库或映射证据，禁止问号替换；
- `overlap_or_alias_conflict`：区分共享资源和冲突编辑，不能最后写入获胜；
- `budget_exceeded`：停止并保留报告，不能静默截断；
- `runtime_not_tested`：输出可供试注的文件，但状态仍是 `not_verified`。

## 归档/引擎边界

如果一个归档已有可靠 writer，但脚本未知，能力可写成 `archive.repack=verified, engine.extract=not_verified`；如果脚本能回填但容器索引未知，写成相反状态。不要用“整包工具”作为单一布尔值。
