# v1.04 LLM 净收益与成本 / Net benefit and cost of the LLM arm

分母 / denominator: 93 个 v1.03 前端可翻译用例。臂 D 为冻结的 v1.03 确定性单元（0 次模型调用），臂 L 为"仅 LLM 原子 + Houdini + 未改动验证器"，每个（用例, 模型）重复 3 次，温度 0.7。 Arm D is the frozen v1.03 deterministic units; arm L adds LLM-proposed atoms only.

- 臂 D 证明 / arm D proved: **88/93**

| 模型 / model | L 证明 (任一/多数) | 仅 D | 仅 L | 配对 McNemar p | 调用 | tokens | 生成秒 |
|---|---|---|---|---|---|---|---|
| `deepseek-v4.1-flash-ark` | 90 / 90 | 0 | 2 | 0.5 | 299 | 2964369 | 16820.3 |
| `claude-sonnet-4-5-20250929` | 89 / 87 | 3 | 2 | 1 | 315 | 1049181 | 9818.0 |

- 全部模型并集 / union of the 2 models: 证明 91/93，仅新增 / net-new 3

- 判定 / verdict: 净新增 3 个程序 / 3 net-new programs; 最小 McNemar p = 0.5; 只有 p < 0.05 才写"有净收益"，且必须同时给出成本；任何情况下不折算成加速 / claim a benefit only at p < 0.05 and always with its cost; never a speedup claim

## 净新增程序 / net-new programs

- `deepseek-v4.1-flash-ark`: ['termination-restricted-15/ex3a.c', 'termination-restricted-15/java_Sequence.c']
- `claude-sonnet-4-5-20250929`: ['termination-restricted-15/McCarthyIterative.c', 'termination-restricted-15/java_Sequence.c']

## 稳定性 / stability

- `deepseek-v4.1-flash-ark`: 重复间判定不一致的用例 1 个 / 1 cases disagree across repeats
- `claude-sonnet-4-5-20250929`: 重复间判定不一致的用例 4 个 / 4 cases disagree across repeats

## 生成健康度 / generation health

一个撞到冻结的 `max_tokens` 上限或返回空内容的响应，会让臂 L 在构造上等于臂 D，不能读成"原子无用"。 A response that hits the frozen cap or comes back empty makes arm L equal arm D by construction.

- `deepseek-v4.1-flash-ark`: 调用 299，撞上限 48，空内容 43，finish length=48, stop=251
- `claude-sonnet-4-5-20250929`: 调用 315，撞上限 33，空内容 0，finish length=2, stop=313

## 成本 / cost

- 臂 D：0 次模型调用，0 token。 Arm D: zero calls.

- `deepseek-v4.1-flash-ark`: 每单位中位调用 1；每个净新增证明 149.5 次调用 / 1482184 tokens / 8410.2 s
- `claude-sonnet-4-5-20250929`: 每单位中位调用 1；每个净新增证明 157.5 次调用 / 524590 tokens / 4909.0 s
