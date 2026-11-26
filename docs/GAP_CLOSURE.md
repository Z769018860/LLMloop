# 缺口清单的处置（v1.07，2026-11-27）/ What happened to each gap

`docs/TOP_TIER_AUDIT.md` §4.10d(c) 列了 6 项。这份文件逐项交代**它现在是什么状态**，以及
"为什么不是全部关掉"。三句话概括：

- **两项关掉**（第 5 项证明不需要跑，第 4 项诊断清楚并改写了它的估计）；
- **论文层面五项本轮做完**（摘要重写、引言、参考文献 23 条、相关工作、结论）；
- **三项要花钱，卡在同一件事上**：这台机器上没有 `LLM_API_KEY`，也没有能派发 Actions 的凭据。
  三项合计 **约 $2.06**，命令都写好了；作者已恢复余额，缺的只是把密钥放进这台机器的环境变量（或改为 CI 派发）。

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

## 3. 第 1、2、3 项：要花钱的三项 —— **准备好了，但没跑**

| # | 缺什么 | 规模 | 估算 | 现在的状态 |
| --- | --- | --- | --- | --- |
| 1 | E6b 的 231 次 void 调用（`deepseek` @16k 写契约） | 231 次调用 / ~98.7k prompt / 1.34–1.42 M completion | **$0.82–0.86** | 协议已冻结（`experiments/v106/e6b/`），只需重跑 `run` |
| 2 | E6c 的重复间一致性（被砍掉的 best-of-3） | 166 次 | **$0.04** | 需要 `repeats=3` 的新冻结（现协议 `repeats=1`） |
| 3 | 第二个价位的契约臂（`claude-sonnet-4-5`，83 次） | 83 次 | **$1.2** | 需要新冻结的 `v108` 规格（现无 runner） |
| | **合计** | **480 次调用** | **≈ $2.06** | |

**为什么没跑。** 三条都不是"想不想"的问题：

1. 这台机器上 `LLM_API_KEY` / `LLM_BASE_URL` 不存在（`env` 里没有，仓库里按纪律也没有），
   它们只以 GitHub Secrets 的形式存在；
2. `gh` CLI 未安装，也没有 `GITHUB_TOKEN` / `~/.config/gh/hosts.yml`，**无法派发 workflow**；
3. 更关键：E6b 那 231 次**不是模型拒绝，是账户余额被打到负数**（v1.07 工作流注释里写着
   "18 of 249 units answered before the account balance went negative"）。**余额不先修，重跑只会
   生成 231 行新的 void。**

**钥匙到手后要跑的三条命令**（按此顺序，前两条不改代码）：

```bash
# 1) E6b 补 void：先删掉 231 个失败单元的 raw 目录（它们没有内容，留着会被当成"已完成"跳过）
python scripts/spec_v106.py run --output experiments/v106/e6b --workers 4
python scripts/spec_v106.py merge --output experiments/v106/e6b

# 2) E6c 重复一致性：需要先把 repeats 从 1 改成 3 并重新冻结（这会改 protocol.json，属于新实验）
python scripts/spec_v107.py freeze --output experiments/v108/e6d
python scripts/spec_v107.py run    --output experiments/v108/e6d --workers 4
python scripts/spec_v107.py merge  --output experiments/v108/e6d

# 3) 第二个价位：复制 spec_v107 → spec_v108，MODEL 换成 claude-sonnet-4-5，再 freeze/run/merge
```

跑完之后的动作是固定的：`python scripts/llm_ledger.py`（总账会把新行并进去）、
`python scripts/check_protocols.py`（新协议应当 `amended` 而不是 `DRIFT`）、
`python -m pytest -q tests/test_spec_v10{6,7}.py`。

**没有一项会改变主结论。** 第 1 项把"一个价位"放宽成"两个模型、两个上限"；第 3 项把它放宽成
价格趋势；第 2 项只影响措辞的宽窄。§4p 那句"这一臂上模型落后"的边界不会因为这三项而移动。

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
| 1 | E6b void | **阻塞**（余额 + 钥匙） | 命令见 §3，$0.85 |
| 2 | E6c 重复一致性 | **阻塞**（钥匙） | 命令见 §3，$0.04 |
| 3 | 第二价位 | **阻塞**（钥匙 + 需新规格） | 命令见 §3，$1.2 |
| 4 | `KeyError:'temp'` | **关闭（诊断 + 不改代码）** | `docs/EGCD3_TEMP.md` |
| 5 | 对照最后盒子 | **关闭（不需要跑）** | §4.10d(c) 已改写 |
| 6 | 参考文献 | **关闭** | `paper/REFERENCES.md`、`scripts/check_references.py --live` |
| 6 | 摘要 / 引言 | **关闭** | 论文 §摘要（含 C1–C5）、§引言 |
| 6 | 相关工作 / 结论 | **关闭** | 论文 §1c、§8 |
| 6 | 两张图 | **未做**（缺排版决定） | — |
