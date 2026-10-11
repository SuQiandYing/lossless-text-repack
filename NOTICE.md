# Notice

本目录完整保留 `lossless-text-repack` skill 的入口、21 份规范、检查脚本和测试；统一引擎目录、适配器契约、标准 JSON 投影、候选检测和阶段能力记录与这些规范共用同一套术语。

`catalog/engines.json` 的 95 个条目是本 skill 的引擎/格式族能力索引；每项都已绑定 `engines/` 页面和随包参考模块，但针对具体输入的提取、回封和运行时阶段仍保持 `catalog-only`/`not_verified`，直到对应证据齐全。

每个引擎模块都必须在 `provenance/` 中记录来源、文件、符号范围、许可证、改动说明和适用测试，并按原许可证分发。仅有算法资料或目录登记不会自动授予 writer 能力。
