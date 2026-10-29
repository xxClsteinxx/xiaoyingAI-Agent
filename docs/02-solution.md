# 02 方案设计

## 调用流程

```text
请求
  ↓
模型选择 read_asset → 观察元数据
  ↓
模型选择 check_rules → 观察 approved / incomplete / blocked
  ├─ incomplete / blocked → 结束并说明原因
  ↓ approved
模型选择 query_slots → 观察冲突和可用备选
  ├─ 硬性时段冲突 / 无备选 → 结束并请求确认
  ↓ 可用要求时段，或有可用备选
模型选择 save_draft → 观察 saved / duplicate / failure
  ↓
模型选择 finish → 输出结构化结果
```

这不是把决策日志预先写死在 Agent 里：`SchedulingAgent` 每一轮只把请求和历史工具观察交给决策模型，模型返回下一动作；工具执行结果再进入下一轮。真实模式中，每轮动作来自模型结构化输出。离线模式实现相同接口的确定性策略，便于无密钥复现流程，其边界已在输出的 `real_model: false` 和文档中明确。

两条关键动态路径：

- `18:00` 可用：`query_slots` 后直接保存 `18:00`，`confirmation_status=not_required`。
- `18:00` 已占用：观察到冲突后改选可用的 `19:00`，保存为 `pending_user_confirmation`；若它是硬性要求，则不调用保存工具。

## 决策与确定性边界

模型适合选择“下一步查什么/是否结束/采用哪个备选”；确定性的业务约束不应只靠提示词。因此 `save_draft` 会独立复核：

- 实际规则结果必须为 approved，不能相信模型传入的字符串；
- 拟定时段不能已占用；
- 硬性要求不能改时；
- 改时必须为 `pending_user_confirmation`；
- 相同 request_id 和载荷幂等，不同载荷报 idempotency conflict；
- 只写 `state=draft, published=false`。

最终结果还会用实际工具观察校正模型表述。没有成功的保存观察时，即使模型声称已保存，也会返回 `incomplete_model_termination`。

## 技术取舍

- Python 标准库：减少评审安装摩擦，当前实现兼容 Python 3.7+。
- 原生 Agent 循环：代码体量小，能清楚展示决策边界、Trace 和步数上限；此题不需要框架的状态图、持久化 checkpoint 或多 Agent 能力。
- JSON Mock 工具：验证业务流程和异常，不冒充外部服务效果。
- OpenAI Responses API：真实模式用结构化 JSON action，模型逐轮接收观察并选择下一动作。这里不让托管 API 自动执行本地函数，便于在本地统一执行工具校验和审计。
- 原子文件替换：足够演示单进程草稿保存；生产环境应换为带唯一键和事务的数据库。

模型接口依据 OpenAI Responses API 的 `instructions`、`input` 与结构化 `text.format` 设计；官方参考：[Create a model response](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)。

## 失败策略

模型/API 失败返回 `model_failed`；工具参数错误以观察返回，让模型有机会调整；保存失败必须结束为 `save_failed`；最多默认 6 步，耗尽返回明确未完成状态。Trace 不保存模型内部思维，仅保存简短业务依据。

