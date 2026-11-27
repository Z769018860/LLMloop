# v0.98 报告 / Report (中文 / English) — 补上"找违例"的缺口:可重放的动态证伪器

## 中文
**缺口。** 此前我们只能证明程序无未定义行为,不能找违例:在 NoOverflows 集的 106 个有溢出程序上,我们 0 个被认证(这是正确的),但也不能给出"确实溢出"的判定;Ultimate 找到 100 个、ESBMC 101 个。
**做法(`scripts/falsify_v098.py`,不受信的搜索 + 可检查的结果)。** 原始基准文件用 clang `-O0 -fsanitize=signed-integer-overflow -fsanitize-trap=all` 本地编译,链接一个驱动:用带种子的 PRNG 实现 `__VERIFIER_nondet_*`,取值偏向边界(0、±1、MIN、MAX、MAX−1、小值、均匀)。运行至陷阱(SIGILL)即得到**具体的、可重放的见证(程序 + 种子)**。它只可能报告真实溢出(重放即可复核),不会产生误报,也不证明任何东西;每个程序预算 15 s、最多 600 个种子、单次运行 2 s 超时。
**结果。** 173 个程序(67 个预期无溢出,106 个预期有溢出):有溢出的 **106 个中找到 100 个见证**;无溢出的 67 个 **0 个见证**(与证明一致,无矛盾)。**100 个见证全部重放确认**(同种子再编译再运行,均触发陷阱)。
**合起来的判定(证明 + 见证)。**

| 方法 | 已判定 | 证明 | 违例/见证 |
|---|---|---|---|
| 我们(Houdini + LLM 原子 + 证伪器) | **159/173** | 59 | 100 |
| Ultimate(100 s + 420 s 重跑) | 156/173 | 56 | 100 |
| ESBMC | 105 | 4 | 101 |
| CBMC | 99 | 7 | 92 |
| CPAchecker | 42 | 42 | 0 |

我们独有 9、Ultimate 独有 6;任何工具均无错误判定。我们未判定的:8 个无溢出(含 `parity`、`nestedLoop-1`、`Benghazi`)和 6 个有溢出程序(见 `experiments/v098/decision_table.json`)。我们的**每一个判定都可独立检查**:证明带 CBMC 复核过的证书(见 v0.97),违例带可重放的见证;Ultimate/ESBMC/CBMC/CPAchecker 的判定在本实验中**没有**做独立复核。
**判断。** 这补上了"不能找违例"的缺口;与 Ultimate 的差距现在是 159 对 156(配对 9 对 6),**统计上仍然持平**。不能主张"优于 Ultimate":差 3 个程序不显著;开发后数字;证伪器是随机测试(找不到某些需要精确输入的违例);工具未做见证复核。
**局限。** 证伪器是随机测试,不保证找到;性质为 signed-overflow(与我们验证器检查的 UB 集合不同);ILP32 程序按 LP64 编译,但这 16 个 ILP32 程序里没有使用 `long` 的见证问题(重放确认,且无 ILP32+long 的见证被计入);数据来源与前几轮同一集合(已用于开发)。
## English
**Gap.** We could only prove UB-freedom, not find violations: on the 106 overflowing programs of the NoOverflows set we certify 0 (correct) but could not report "does overflow"; Ultimate finds 100, ESBMC 101.
**Method (`scripts/falsify_v098.py`, untrusted search + checkable result).** The original benchmark file is compiled natively with clang `-O0 -fsanitize=signed-integer-overflow -fsanitize-trap=all` and linked with a driver implementing `__VERIFIER_nondet_*` with a seeded PRNG biased to boundary values. A trap (SIGILL) is a **concrete, replayable witness (program + seed)**. It can only report real overflows and proves nothing; budget 15 s / up to 600 seeds per program, 2 s per run.
**Results.** 173 programs (67 overflow-free, 106 overflowing): **100 of 106 overflowing programs get a witness**; **0 witnesses on the 67 overflow-free** (consistent with the proofs). **All 100 witnesses replay** (same seed, recompiled, traps again).
**Combined decisions (proof + witness):** ours **159/173** (59 proofs + 100 witnesses), Ultimate 156 (56 + 100), ESBMC 105, CBMC 99, CPAchecker 42; ours-only 9, Ultimate-only 6; no tool gives a wrong verdict. Undecided by us: 8 overflow-free and 6 overflowing programs (`experiments/v098/decision_table.json`). **Every one of our decisions is independently checkable** (proofs carry CBMC-re-checked certificates, violations carry replayable witnesses); the tools' decisions were **not** independently re-checked here.
**Judgement.** The "cannot find violations" gap is closed; the gap to Ultimate is now 159 vs 156 (paired 9 vs 6), **still statistically a tie**. "Better than Ultimate" is not supported: 3 programs is not significant, post-development numbers, the falsifier is random testing (misses violations needing precise inputs), and the tools' verdicts were not witness-validated.
**Limits.** Random testing gives no guarantee; the property is signed overflow (our verifier checks a larger UB set); ILP32 programs were compiled as LP64, but no ILP32 witness program uses `long` (replay confirmed, none counted); same set as earlier rounds (already used for development).
