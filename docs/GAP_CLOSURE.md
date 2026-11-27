# 缺口清单的处置（v1.07，2026-11-27）/ What happened to each gap

`docs/TOP_TIER_AUDIT.md` §4.10d(c) 列了 6 项。这份文件逐项交代**它现在是什么状态**，以及
"为什么不是全部关掉"。三句话概括：

- **六项全部关闭。**
- **两项零成本**（第 5 项证明不需要跑，第 4 项诊断清楚并改写了它的估计）；
- **论文层面五项做完**（摘要重写、引言、参考文献 23 条、相关工作、结论）；
- **三项付费实验于 2026-11-27 跑完**，实付 **$1.24**（原估 $2.07，贵的那一项估高了：两个新臂的
  回答只有 9–30 个 token，不是 2,000）。**两项给出了新结果，其中一项推翻了正文里的一句话。**

---

## 1. 第 5 项：对照最后一个未试盒子 —— **关闭，不需要跑**

`egcd3-both-t` 的 `uniform@0.01` 保留域是 **9.99999e-5**，卡在 `1e-4` 这一级**之下**。它证出来
也只动两级（`t=0` 的仅 B 13→14、`t=1e-5` 的仅 B 10→11），方向不变且更显著。**已经从缺口清单里
移出**（`TOP_TIER_AUDIT.md` §4.10d(c) 第 5 条已改成"已关闭"）。

## 2. 第 4 项：`egcd3-both-nt` 的 `KeyError: 'temp'` —— **诊断完成，估计被改写**

原估计"改代码，1 小时，$0"。实际是**三个独立障碍**，第三个是语义决策：

| 阶段 | 判定 |
| --- | --- |
| 原样 | `STUCK:Loop bodies must not contain break/continue/return/declarations` |
| 5 个声明提升到函数头（语义等价） | `STUCK:Initialized named scalar locals required` |
| 再给 `= 0`（**不**语义等价） | `STUCK:.../loop2/body operations defined` |

真正的缺陷不是"少一个键"，是**同一份字节在 CI 给 `ERROR`、在本机给 `STUCK`**——一个被前端拒绝的
程序应当稳定地报"片段之外"。该格的正确标签是 `UNSUPPORTED`，计数不变（三种都算"未证出"）。
**本轮不改 `llmloop/`**：动它会 `DRIFT` 三份冻结协议，而本文的中心主张是"验证器一行未改"。
完整论证与可重跑的三行输出：`docs/EGCD3_TEMP.md` + `scripts/diagnose_egcd3.py`。

## 3. 第 1、2、3 项：三项付费实验 —— **已跑完，$1.24**

| # | 实验 | 规模 | 估算 | **实付** | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | E6b 补 void（`deepseek` @16k） | 233 单元补齐 | $0.83–0.87 | **$0.95** | 249/249；13/83 对 17/83，**p = 0.289** |
| 2 | E6e 重复一致性（`gpt-4.1-mini` × 3） | 166 次付费 + 83 缓存 | $0.04 | **$0.05** | 78/83 判定一致；5 例翻转；47 例保留域漂移 |
| 3 | E6d 第二价位（`claude-sonnet-4-5`） | 83 次 | $1.2 | **$0.24** | 4/83，1 对 14，**p = 0.000977** |
| | **合计** | **482 次规划调用** | **$2.07** | **$1.24** | |

### 3.1 第 1 项把结论翻了过来

补齐后 deepseek @16k 证出 **13/83**，对照 17/83，`t = 0` 上仅 S 2、仅 B 6、**p = 0.289（不显著）**。
而两个 2048 上限的臂是 4–5/83、p ≈ 0.001。**也就是说"模型更差"取决于上限**，而这篇文章的主题
正是"上限是混淆变量"。它同时推翻了 §4p 里"在 `t = 0.5` 上模型一个独有证明都没有"这条跨臂断言
（deepseek 在 16k 上有 2 个）。已写进论文 **§4r**，并回改了 §4p 与 §4q(a)。

### 3.2 第 2 项撞到一个陷阱：缓存把"三次"压成了"一次"

第一次运行 27 个单元、`papered_calls: 0`、三次全同——因为缓存键是
`(model, messages, temperature, max_tokens)`，不含抽样序号，三次抽样命中同一个缓存条目。
测出来的"完全一致"是缓存的性质，不是模型的性质。**那 27 个单元被删除，不是被重新解释。**

修法：repeat 0 允许命中缓存（它就是 v1.07 已付费的那一行），repeat 1–2 一律 `use_cache=False`。
回归测试在 `tests/test_spec_v109.py`。

### 3.3 第 3 项比估价便宜五倍

估算按"每次回答 ~2,000 token"算，实际 `claude-sonnet-4-5` 的回答中位 **9–30 token**（任务只要求一个
JSON 盒子）。83 次调用共 38,614 prompt + 8,263 completion，**$0.24**。

### 3.4 一个不属于缺口的开关：Windows 上的 POSIX 原语

第一次尝试在发出任何请求之前崩了 249 次：`os.wait4` / `os.killpg` / `signal.SIGKILL` 是 POSIX 专有。
`scripts/resource_capture.py` 在 `frozen_source_sha256` 里，**不能改**，所以在外面补一层
`tools/wincompat/sitecustomize.py`（`PYTHONPATH=tools/wincompat`）。验证器一个字节未动。
代价与边界写在 `docs/WINDOWS_PORT.md`：`command.json` 的 CPU 两列在 Windows 上可能是 0。

### 3.5 复跑这三项

```bash
export LLM_API_KEY=...                    # 不落盘、不进仓库
export PYTHONPATH=tools/wincompat         # 只在 Windows 上需要

python scripts/spec_v106.py preflight --output experiments/v106/e6b   # 1 次调用，先问账户能不能答
python scripts/merge_unsharded.py         # E6b 是无分片跑的，v1.06 的 merge 只认分片
python scripts/spec_v108.py check && python scripts/spec_v108.py merge
python scripts/spec_v109.py check && python scripts/spec_v109.py merge
python scripts/e6e_consistency.py         # 三次抽样的离散度，零调用
python scripts/llm_ledger.py              # 总账：2,912 次 / $26.98
```

## 4. 第 6 项：论文层面 —— **本轮做完**

| 工件 | 之前 | 现在 |
| --- | --- | --- |
| 摘要 | 7 段里 4 段是带日期的更新 | 中英各一段（可靠性 / 覆盖率 / 边际价值）+ C1–C5 + 四条不声称 + 版本说明 |
| 引言 | 缺（摘要第一段兼任） | §引言：问题 / 为什么难三条 / 做法 / 贡献 / 不声称 / 结构 |
| 参考文献 | **0 条**，正文 0 个 `[n]` | **23 条**，每条有 DOI/arXiv + 开放 PDF，`--live` 23/23 返回 `application/pdf` |
| 相关工作 | 缺 | §1c，六簇，每簇说清"差在哪"而不是"他们做了 X" |
| 结论 | 缺（§7 复现被当成结论） | §8，C1–C3 + 一句边界，**不含**"模型更差" |
| 图 | 0 张 | 仍缺（见下） |

**图仍然缺。** 两张图（流水线、E6c 阶梯）的数据都在仓库里，但作图不属于本轮"补齐缺口"的最小
闭环；它需要决定排版工具（TikZ 还是 SVG），而这取决于投哪里。**这是唯一一项"知道怎么做、
但缺少一个上游决定"的**。

## 5. 状态汇总

| # | 缺口 | 状态 | 证据 / 命令 |
| --- | --- | --- | --- |
| 1 | E6b void | **关闭**（$0.95；249/249，13/83 对 17/83，p = 0.289） | `experiments/v106/e6b/summary.json`，论文 §4r |
| 2 | 重复一致性 | **关闭**（$0.05；78/83 一致、5 例翻转、47 例漂移） | `experiments/v109/e6e/consistency.md`，论文 §4q(b) |
| 3 | 第二价位 | **关闭**（$0.24；4/83，1 对 14，p = 0.000977） | `experiments/v108/e6d/summary.md`，论文 §4q(a) |
| 4 | `KeyError:'temp'` | **关闭（诊断 + 不改代码）** | `docs/EGCD3_TEMP.md` |
| 5 | 对照最后盒子 | **关闭（不需要跑）** | §4.10d(c) 已改写 |
| 6 | 参考文献 | **关闭** | `paper/REFERENCES.md`、`scripts/check_references.py --live` |
| 6 | 摘要 / 引言 | **关闭** | 论文 §摘要（含 C1–C5）、§引言 |
| 6 | 相关工作 / 结论 | **关闭** | 论文 §1c、§8 |
| 6 | 两张图 | **未做**（缺排版决定） | — |
