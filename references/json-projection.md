# JSON 投影规范

JSON 投影是 IR 的轻量编辑面，适合交给翻译工具或脚本处理。它只保存可编辑正文和必要的身份信息；结构、控制码、编码与定位证据放在同目录的 manifest 中，回封前必须重新从源生成 IR 并校验。

## 工作目录

```text
<result>/
  text_input/    # 非空、可编辑 message 的 UTF-8 JSON
  text_output/   # 用户译文，按同名返回
  metadata/      # manifest、locator、控制码和编码
  original/      # 选定成员的哈希绑定原件
  reports/       # 阶段状态和失败诊断
```

JSON 保持简单的列表形状：

```json
[
  {"name": "角色", "message": "对白"},
  {"message": "旁白"}
]
```

姓名位于正文前；旁白省略 `name`。多人名、显示槽、变量姓名和命令属性放入 manifest，不把它们拼进正文。原脚本编码与 JSON UTF-8 分开记录。

## Sidecar 行契约

每个 JSON 旁边保存 `<stem>.manifest.json`，最小内容为：

```json
{
  "schema": "lossless-text-repack.json-manifest/1",
  "projection": "json",
  "source_sha256": "...",
  "engine": {"id": "...", "dialect": "..."},
  "rows": [
    {"row_id": 0, "entry_id": "...", "source_text": "原文",
     "name_policy": "writable", "controls": [],
     "locator": {"member": "...", "offset": 0, "length": 0, "unit": "bytes"}}
  ]
}
```

导入时严格核对源哈希、row/entry 集合、侧车顺序、原文、姓名策略、控制码和 locator。缺译文保留原文；缺 row、改侧车顺序、改原文锚、改只读姓名、注入未知控制码或来源变更都在写出前失败。JSON 列表按位置映射；只有译文内容而没有行身份时，单独交换行无法从数据上识别，因此编辑流程必须保留行序。

## 与双编辑面合并

同一 entry 可以同时出现在 JSON 和 ASM 中。两面提交相同改动时合并为一个 ChangeSet；不同改动产生冲突，不能使用“最后写入获胜”。ASM 只用于定位和审计，不能绕过 parser 直接提交任意十六进制。

## 回填状态

`text_input` 生成成功只代表投影通过；把译文放入 `text_output` 后还要执行 manifest 校验、严格编码、引用闭包、重解析和外层回封。没有实际启动宿主时，交付表中的运行时状态写 `not_verified`。
