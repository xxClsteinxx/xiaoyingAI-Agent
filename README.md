# 素材审核与发布排期 Agent

校招 AI Agent 开发考核第 1 题。项目用一个有步数上限的 Observe → Decide → Act 循环，完成素材读取、规则审核、时段检查和**草稿**保存。模型可以根据工具结果改选下一步；业务工具始终执行安全校验，因此模型不能越权发布、绕过风险或静默改掉硬性时间。

## 评审快速入口

环境：Python 3.7+，运行与测试均仅用标准库，无需安装依赖、无需密钥。

```bash
# 1. 运行冲突改期路径（18:00 占用，建议 19:00，待确认）
python -m src.scheduler_agent.cli --input data/requests/conflict.json --draft-store runtime/review-drafts.json

# 2. 再运行一次相同命令（返回 draft_exists，草稿数量仍为 1）
python -m src.scheduler_agent.cli --input data/requests/conflict.json --draft-store runtime/review-drafts.json

# 3. 执行全部测试
python -m unittest discover -s tests -v
```

建议依次查看：

- [需求与成功标准](docs/01-requirements.md)
- [调用流程和动态决策](docs/02-solution.md)
- [实际验证结果](docs/03-evaluation.md)
- [AI 使用声明](docs/04-ai-usage.md)
- [复盘](docs/05-retrospective.md)
- [冲突改期实际 Trace](examples/02-conflict-output.json)
- [保存失败实际 Trace](examples/06-save-failure-output.json)
- [测试实录](examples/test-results.txt)

## 运行更多场景

```bash
python -m src.scheduler_agent.cli --input data/requests/normal.json
python -m src.scheduler_agent.cli --input data/requests/missing.json
python -m src.scheduler_agent.cli --input data/requests/risk.json
python -m src.scheduler_agent.cli --input data/requests/save_failure.json

# 验证步数上限（明确返回 incomplete_step_limit）
python -m src.scheduler_agent.cli --input data/requests/normal.json --max-steps 2

# 重新生成 examples/ 中的实际输出和测试实录
python scripts/generate_examples.py
```

CLI 对业务阻断（缺资料、规则风险、需确认）返回进程码 0，因为 Agent 已正确完成判断；配置错误、模型/保存失败、步数耗尽返回非 0。输出字段包含审核状态、风险原因、建议时段、确认状态、保存状态、`published: false` 和逐步 Trace。

## 真实模型模式

离线模式默认使用透明的决策 Mock，只证明流程和工程边界，不作为真实模型决策效果证据。配置 `.env.example` 中变量后，可让真实模型逐轮选择动作：

```bash
set OPENAI_API_KEY=your-key
set OPENAI_MODEL=gpt-5-mini
python -m src.scheduler_agent.cli --model openai --input data/requests/conflict.json
```

PowerShell 使用 `$env:OPENAI_API_KEY="your-key"`。模型适配层调用 OpenAI Responses API 的结构化 JSON 输出；也可通过 `OPENAI_BASE_URL` 接兼容端点。项目没有内置或提交任何密钥。

## 目录

```text
src/scheduler_agent/  Agent 循环、模型适配器、业务工具
tests/                11+ 个可执行单元/集成测试
examples/             程序生成的输入对应输出、Trace、测试实录
data/                 合成素材、审核规则、已有排期、请求
docs/                 需求、方案、评估、AI 使用、复盘
scripts/              验证材料再生成脚本
```

## 明确边界

- 本项目只保存草稿，没有任何发布工具。
- 替代时段只形成 `pending_user_confirmation` 草稿，不代表用户已同意。
- 本地 JSON 模拟素材库、规则服务、排期服务和草稿库；没有处理真实素材或隐私数据。
- 本地保存使用原子替换和请求 ID 幂等，但没有实现多进程锁、数据库事务、鉴权和线上可观测性。

