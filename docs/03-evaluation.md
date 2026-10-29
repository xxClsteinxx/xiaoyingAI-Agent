# 03 效果验证

## 方法与实际结果

验证命令：

```bash
python scripts/generate_examples.py
python -m unittest discover -s tests -v
```

本次实际结果：13 个测试全部通过（含 9 个 Agent 场景测试与 4 个工具护栏测试）；原始实录见 [test-results.txt](../examples/test-results.txt)。验证材料均由 `scripts/generate_examples.py` 调用同一业务代码生成，避免手工拼 Trace。

| 场景 | 预期 | 实际 | 证据 |
|---|---|---|---|
| 正常 | 原时段保存草稿，无需确认 | `draft_saved` | [01](../examples/01-normal-output.json) |
| 冲突 | 18:00 冲突，建议 19:00，待确认 | 符合；未发布 | [02](../examples/02-conflict-output.json) |
| 重复 | 复用同一 draft，不新增 | `draft_exists`, duplicate=true | [03](../examples/03-conflict-duplicate-output.json) |
| 信息缺失 | 缺字段，查时段前结束 | 缺 `target_channel`，未保存 | [04](../examples/04-missing-output.json) |
| 规则风险 | 命中风险并阻断 | `BLOCKED_WORD`，未保存 | [05](../examples/05-risk-output.json) |
| 保存失败 | 明确失败，不虚报保存 | `save_failed`, saved=false | [06](../examples/06-save-failure-output.json) |

自动化测试还验证：硬性时段不可擅改、步数上限、Trace 必要字段、模型谎报审核无法绕过工具、占用时段无法保存。

## 两条决策路径对比

正常路径观察到 `requested_available=true`，下一动作是按要求时段保存，确认状态为 `not_required`。冲突路径观察到 `requested_available=false`、`available_alternatives=[19:00]`，下一动作改为保存 19:00 并设置 `pending_user_confirmation`。两条路径的步骤 3/4 可直接在 01 与 02 Trace 对照。

## 失败与限制

- 当前提交没有真实 API key，因此已提交 Trace 来自离线决策 Mock，只证明循环、工具、护栏和输出，不证明真实模型选择准确率。
- `simulate_save_failure` 是可控故障注入，用于验证失败语义；不是对真实数据库可用性的测量。
- 测试数据为合成数据，规则较少；真实效果需要业务规则集和标注用例回放。
- 本地 JSON 幂等不覆盖多进程竞争。生产方案需数据库唯一约束 `(request_id)`、载荷 hash 和事务。
- 真实模型可能选错工具或参数；目前有工具护栏和步数上限，但未实现一次结构化纠错重试或模型质量统计。

## 后续评估

接入真实模型后，用至少 50 条标注请求测量：正确终态率、风险漏放率（应为首要指标）、错误改动硬性要求率（目标 0）、冲突备选正确率、平均工具调用数和 P95 延迟。真实模型 Trace 应单独提交，不能与 Mock 结果混称。

