# 04 AI 使用声明

## 使用范围

本项目允许使用 AI 辅助，本仓库采用了较高比例的 AI 协作。候选人向 OpenAI Codex 提供完整考核原题、选择第 1 题，并指定最终 GitHub 仓库；Codex 完成需求拆解、方案设计、代码实现、合成数据、测试用例、示例 Trace、文档初稿、本地验证、Git 提交及推送。

Codex 还检索了官方 OpenAI Responses API 文档，用于核对真实模型适配层的请求方式；根据本地执行结果修复了示例生成脚本，并补充了工具层安全护栏。

AI 未执行或无法证明的内容包括：

- 没有使用真实业务数据或调用真实发布接口；
- 没有使用候选人的模型 API Key；
- 没有生成真实模型运行 Trace，已提交 Trace 均明确标记为离线 Mock；
- 没有完成线上部署、生产数据库或人工确认回写；
- 没有代替候选人虚构个人编码经历、模型效果或业务验证结论。

## 候选人贡献

候选人的直接贡献为：提供完整需求和验收规范、选择素材审核与发布排期题目、指定代码仓库并发起最终交付。代码、测试和文档主体由 Codex 生成，因此本项目不声明为候选人独立手写。

候选人在提交与面试中应以仓库中的可执行测试和 Trace 为依据说明项目，不把离线 Mock 结果表述为真实模型效果。

## AI 产物后的工程校验

Codex 实际执行了以下验证：

```bash
python scripts/generate_examples.py
python -m compileall -q src scripts tests
python -m unittest discover -s tests -v
python -m src.scheduler_agent.cli --input data/requests/save_failure.json
python -m src.scheduler_agent.cli --input data/requests/normal.json --max-steps 2
```

结果为 13 个自动化测试全部通过；保存失败返回非零退出码且不虚报成功；步数耗尽返回 `incomplete_step_limit`；11 个 examples JSON 文件均可按 UTF-8 正常解析。原始测试实录位于 `examples/test-results.txt`。

## 实际投入时间

从空目录开始实现到首次完整提交，AI 执行会话约 15 分钟（2026-10-29 16:40—16:55，Asia/Shanghai），包括实现、文档、测试、修复和推送。候选人侧未单独记录开发时长，其投入主要是提供题目、确认交付范围与仓库地址。

