# v1.04 LLM 净收益与成本：冻结前的设计 / Net benefit and cost of the LLM arm: design, not yet frozen

状态 / status: **设计稿，未冻结**。没有驱动、没有凭据、没有任何结果。按本项目惯例，协议必须在第一次调用模型之前冻结，因此这里只登记设计与预注册的分析口径；驱动与 `protocol.json`（含驱动哈希）在拿到凭据后再冻结。 Design only: no driver, no credentials, no results. As elsewhere in this project the protocol must be frozen before the first call, so only the design and the pre-registered analysis are recorded here.

## 为什么需要这个研究 / why this study is needed

v1.03 的 165 分母对照（`experiments/v103/full165/`）**不含 LLM**（`remote_model_calls = 0`）：llmloop 一侧是"默认配置，未证明时再启用既有多项式剖面"的确定性组合。因此那份证据回答的是"确定性能力对 Ultimate"，**没有**回答"LLM 到底加了多少、代价多少"。旧数字（v0.97：67 个开发集程序里 57 个至少一个模型证出、并集 59 对 Ultimate 56）用的是另一个分母，不能搬到 165 上。 The v1.03 comparison contains no LLM at all, so it says nothing about the LLM's contribution; the old v0.97 numbers use a different denominator and cannot be transplanted.

## 设计 / design

- **分母 / denominator.** 冻结的 93 个前端可翻译用例（`full165/protocol.json` 中 `historical_stage` 以 `in_` 开头的项）。其余 72 个在前端即被拒绝（`alloca`/`malloc`/提前 `return`/语句后 `assume`），LLM 提案没有可作用的验证目标，按构造记为未证明，并作为能力边界报告，不计入 LLM 的失败。 The 93 front-end-accepted cases only; the other 72 are rejected before any proposal can be checked.
- **臂 / arms.** `D` 确定性组合（直接复用 v1.03 的原始单元，不重跑）；`L` LLM 原子 + Houdini 弱化 + 未改动验证器；`D∪L` 并集。LLM 只提**原子**，不提议完整不变式、不参与判定。 `D` reuses the v1.03 units unchanged; `L` adds LLM-proposed atoms under Houdini; `D∪L` is the union.
- **模型与采样 / models and sampling.** 2–3 个可用模型，**精确写出端点上看到的模型串**；每个（用例, 模型）重复 **3 次**，温度 0.7，`max_tokens` 固定，重试上限 3 次（指数退避）。所有重复全部报告，不挑选。 3 repeats per (case, model), temperature 0.7, bounded retries; every repeat is reported.
- **预算 / budgets.** 验证侧与 v1.03 相同（600 s 进程组墙钟、2 GiB 采样 RSS）。**生成时间与验证时间分列**：报告"仅验证"与"含生成"两种墙钟，不把模型延迟藏进 600 s 里。 Same verification caps as v1.03; generation latency is reported separately, never folded into the 600 s.
- **记录 / what is recorded.** 每个请求：请求体全文（含提示）、提示哈希、响应全文、HTTP 状态、重试次数与每次延迟、`usage` 的 prompt/completion tokens、端点与模型串、时间戳；每个验证：完整命令行、stdout/stderr、资源与判定，与 v1.03 的原始单元同构。 Full request/response, retries, tokens, latency, endpoint, model string, plus the v1.03-shaped verification record.
- **派生 / outcome derivation.** 与 v1.03 完全相同的判定词表（proved / refuted / undecided / conditional / resource_stop / broken），不自造第二个口径。 Identical outcome vocabulary to v1.03.

## 预注册的分析 / pre-registered analysis

1. **主检验**：93 项上 `D` 与 `L`（每次重复各算一次，重复内取多数）的配对证明比较，精确 McNemar；报告 `L∖D` 的净新增程序数。 Paired McNemar of `D` vs `L` on the 93 cases, per repeat and by majority of 3.
2. **成本**：每个净新增证明的代价 = (`LLM` 调用次数, prompt+completion tokens, 生成墙钟) / max(1, |`L∖D`|)；并报告每程序的中位调用数与 token 数，与 `D` 的零调用对照。 Cost per net-new proof in calls, tokens and generation wall time, against `D`'s zero calls.
3. **判定规则（先写死）**：若 3 次重复的 `L∖D` 并集为 0，论文写"在该预算下未测得 LLM 净收益"；若 >0，只有在 McNemar p < 0.05 时才写"有净收益"，并把成本与净增数一起给出。**任何情况下都不把 LLM 增益折算成"加速"。** Decision rule fixed in advance: zero net-new means "no measurable benefit at this budget"; a positive result needs p < 0.05 and is always reported with its cost; no speedup claim either way.
4. **稳定性**：报告 3 次重复之间的差异（哪些程序只有某一次证出），以及重试率、超时率与截断率。 Repeat-to-repeat variation, retry rate, timeout rate and truncation rate.

## 已知威胁 / threats

模型可能见过公开基准（`termination-restricted-15` 是 SV-COMP 的公开目录）；端点上的模型版本可能漂移，故必须记录模型串与时间；单温度、单提示，不做提示搜索；token 计量依赖端点返回的 `usage`，若缺失则记为不可用而不是估计。 Public benchmarks may be in training data; the served model may drift, so the model string and timestamps are recorded; one temperature and one prompt, no prompt search; tokens come from the endpoint's `usage` and are recorded as unavailable rather than estimated.

## 解锁条件 / what unblocks it

在仓库 secret 里放入 `LLM_API_KEY`（以及可选 `LLM_BASE_URL`），然后：冻结 `protocol.json`（用例、排程、提示哈希、模型串、采样参数、预算、分析口径）→ 提交 → 派发运行。凭据只经 secret 注入，不入库。 Put `LLM_API_KEY` (and optionally `LLM_BASE_URL`) in the repository secrets, then freeze and commit the protocol before dispatching the run.
