# v1.04 LLM 净收益与成本 / Net benefit and cost of the LLM arm

分母 / denominator: 93 个 v1.03 前端可翻译用例。臂 D 为冻结的 v1.03 确定性单元（0 次模型调用），臂 L 为"仅 LLM 原子 + Houdini + 未改动验证器"，每个（用例, 模型）重复 3 次，温度 0.7。 Arm D is the frozen v1.03 deterministic units; arm L adds LLM-proposed atoms only.

- 臂 D 证明 / arm D proved: **88/93**

| 模型 / model | L 证明 (任一/多数) | 仅 D | 仅 L | 配对 McNemar p | 调用 | tokens | 生成秒 |
|---|---|---|---|---|---|---|---|
| `deepseek-v4.1-flash-ark` | 88 / 88 | 0 | 0 | 1 | 309 | 1862587 | 10554.1 |
| `gpt-4.1-mini` | 88 / 85 | 4 | 1 | 0.375 | 342 | 334612 | 1260.9 |
| `claude-sonnet-4-5-20250929` | 89 / 87 | 2 | 1 | 1 | 319 | 717140 | 7163.7 |

- 全部模型并集 / union of the 3 models: 证明 90/93，仅新增 / net-new 2

- 判定 / verdict: 净新增 2 个程序 / 2 net-new programs; 最小 McNemar p = 0.375; 只有 p < 0.05 才写"有净收益"，且必须同时给出成本；任何情况下不折算成加速 / claim a benefit only at p < 0.05 and always with its cost; never a speedup claim

## 净新增程序 / net-new programs

- `deepseek-v4.1-flash-ark`: 无 / none
- `gpt-4.1-mini`: ['termination-restricted-15/McCarthyIterative.c']
- `claude-sonnet-4-5-20250929`: ['termination-restricted-15/java_Sequence.c']

## 稳定性 / stability

- `deepseek-v4.1-flash-ark`: 重复间判定不一致的用例 0 个 / 0 cases disagree across repeats
- `gpt-4.1-mini`: 重复间判定不一致的用例 12 个 / 12 cases disagree across repeats
- `claude-sonnet-4-5-20250929`: 重复间判定不一致的用例 6 个 / 6 cases disagree across repeats

## 成本 / cost

- 臂 D：0 次模型调用，0 token。 Arm D: zero calls.

- `deepseek-v4.1-flash-ark`: 每单位中位调用 1；每个净新增证明 n/a（净新增为 0）
- `gpt-4.1-mini`: 每单位中位调用 1；每个净新增证明 342.0 次调用 / 334612 tokens / 1260.9 s
- `claude-sonnet-4-5-20250929`: 每单位中位调用 1；每个净新增证明 319.0 次调用 / 717140 tokens / 7163.7 s
