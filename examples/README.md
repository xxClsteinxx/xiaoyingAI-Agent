# 验证材料索引

所有 JSON 都是 `python scripts/generate_examples.py` 的实际产物，含完整输入相关结果与 Trace；生成时使用临时草稿库，保证重复场景可复现。

- `inputs/`：用于生成记录的输入快照
- `01-normal-output.json`：正常排期
- `02-conflict-output.json`：冲突后建议替代时段并待确认
- `03-conflict-duplicate-output.json`：同一请求重复提交
- `04-missing-output.json`：素材信息缺失
- `05-risk-output.json`：规则高风险
- `06-save-failure-output.json`：保存工具失败
- `test-results.txt`：自动测试实际输出

这些结果使用 `offline-policy-mock`，只证明工作流与业务工具。真实模型证据应使用 `--model openai` 另行生成并明确标注。
