# v1.02：修正真值标签与独立压力实验 / Oracle repair and independent stress controls

Base: `18d66724bfe94094afc5148ab2bac3dfaef3085d` on the latest experimental branch. No changes to `llmloop/` verifier code. No model calls or GitHub Actions.

## 修复与历史标签 / Repairs and historical labels
The old generator reused one nondeterministic Boolean for the guard and all body calls in a loop iteration. This omitted valid C executions. It also replaced the substring `nd` inside the newly emitted Python `and`, dropping conjunctive guards through caught parsing errors. Both are fixed. Evaluation now checks every intermediate signed-int32 operation, preserves short circuit evaluation and explores independent call choices. State-budget exhaustion is UNDECIDED, never SAFE.

旧的 60 项合成集合未被覆盖。资源上限 10,000 状态的事后审计中，`synth_0010.c` 从 SAFE 反驳为 OVERFLOW，具体输入 a=40。GCC O0、Clang O0/O2 共 3 次原始源码重放均确认。其余预算耗尽项不算标签确认；旧集合不再作为可靠真值集。This is a generator-label defect, not a false certificate from the verifier.

Eight new semantic tests and three targeted oracle mutants cover correlated choices, intermediate overflow, short circuit, negation, cycles, budget exhaustion and unsupported operators. All three deliberately broken oracle implementations are detected. This is not a complete verifier mutation score.

## 冻结集合 / Frozen corpus
First 160 decided cases from 181 attempts, seed 20261122. 114 SAFE, 46 OVERFLOW. All rejected-by-budget attempts are retained. Sources are generated independently of Houdini outcomes, frozen before running proof modes or CBMC.

All variables are 32-bit signed `int`; only input ranges are small. **This is not an 8/16-bit integer study.** SAFE requires the complete reachable loop-header graph (including input values) to close without any intermediate overflow; cycles are allowed, so SAFE is not a termination claim. All nondet calls appear solely as Boolean tests, for which choices 0/1 are exhaustive.

This is one self-authored generator family, not the missing independent external benchmark. The supported scalar grammar and small input domains limit generalization. The initial guard uses a conjunction recognized by the existing translator; this is disclosed corpus design, not evidence of general front-end coverage.

## 完整分母与重复 / Full denominator and repetitions
960/960 outcomes captured: 160 original programs × two modes × three seeds. The original denominator includes any translation errors, process errors and timeouts. Proof modes use the same translated source, input bounds, unchanged verifier and 5 s solver-query limit. Each fresh process has a 30 s host limit, including translation, candidate generation and verification. Houdini uses 60 samples and at most 150 rounds. Trivial mode submits only `True`; Houdini includes its existing trivial-first check.

| Mode | PROVED, seeds 1 / 2 / 3 (each /160) | Unsafe certified /138 | Median process wall s | Host timeouts /480 |
|---|---:|---:|---:|---:|
| trivial | 13 / 13 / 13 | 0 | 0.515 | 0 |
| houdini | 105 / 105 / 105 | 0 | 1.088 | 0 |

配对 bootstrap 以程序为抽样单位（三个种子保持在同一程序内），仅对 114 个 SAFE 程序：Houdini 减 trivial 的平均证明率差 0.807，描述性 95% percentile 区间 [0.737, 0.877]。Only one comparison is made; no multiple-comparison significance claim. Shared-host timing is not a general speedup claim. A failure to prove is not an overflow verdict.

## 原始 C 的独立核验 / Independent original-source audit
CBMC 6.11.0, signed-overflow checks, ILP32, unwind 64 with unwinding assertions, 10 s host deadline, two workers. All 160 original C files are included. A failed unwinding assertion alone is UNKNOWN. Full JSON output and property classes are retained.

| Oracle label | CBMC SAFE | CBMC OVERFLOW | UNKNOWN | Host timeout |
|---|---:|---:|---:|---:|
| SAFE | 31 | 0 | 82 | 1 |
| OVERFLOW | 0 | 38 | 0 | 8 |

Contradictions: 0. This bounded audit corroborates only definite outcomes; UNKNOWN and timeout do not validate labels and do not refute them. This is not a CBMC portfolio or SOTA comparison.

## 见证与翻译差分 / Witness and translation replay
All 46 overflow witnesses are replayed on original and automatically translated source with GCC14 and Clang19 at O0/O2: 368 compiler/source observations, 323 detected overflows. Native nondet streams include the oracle inputs and independent choices. Full build/run output is retained.

| Compiler | Original overflow detected | Translated overflow detected |
|---|---:|---:|
| gcc -O0 | 46/46 | 46/46 |
| gcc -O2 | 25/46 | 22/46 |
| clang -O0 | 46/46 | 46/46 |
| clang -O2 | 46/46 | 46/46 |

GCC O2 sometimes eliminates dead arithmetic before sanitizer instrumentation: 21 original and 24 translated observations did not replay an overflow. Missing traps/timeouts are retained, not converted to SAFE. A representative assembly diagnostic is archived. GCC O0 and Clang O0/O2 detect all 46 witnesses on both sources. This differential replay covers positive witnesses only; it is not universal translator equivalence or a native proof of the SAFE cases.

## 验证与复现 / Validation and reproduction
Full regression not completed; see raw progress, with no full-pass claim.

Synthetic runs use Python 3.12, SymPy 1.12.1, Z3 4.13.0.0 and pycparser 2.22 (the generated grammar is C11). The full repository also exercises C23 label/declaration parsing, so its modern dependency regression uses isolated pycparser 3.0 and Z3 4.15.4. The cubic-prefix obligation that returns UNKNOWN under Z3 4.13 is proved under 4.15.4 at the unchanged query limit (cubic_modern_z3.json). The interrupted old-parser full-suite attempt is archived separately; it is not counted as a complete regression. The initially misconfigured reach-safety translator attempt is also retained and excluded from experiment denominators.

```sh
python -m pytest -q tests/test_synth_oracle_v102.py
python -m scripts.synth_mutations_v102
python scripts/synth_bench_v102.py 160 --output /fresh/corpus
python scripts/synth_experiments_v102.py freeze --corpus /fresh/corpus --output /fresh/study
python scripts/synth_experiments_v102.py run --corpus /fresh/corpus --output /fresh/study --jobs 3
python scripts/synth_experiments_v102.py native --corpus /fresh/corpus --output /fresh/study
python scripts/synth_cbmc_v102.py --cbmc /absolute/cbmc --corpus /fresh/corpus --output /fresh/cbmc
python scripts/report_synth_v102.py
```

The run drivers support resuming captured proof/CBMC commands without replacing previous outcomes. Hash checks reject modified frozen inputs or drivers. Timings are concurrent throughput observations.

## 仍未完成 / Still open
This closes a concrete label bug and adds exhaustive-label synthetic pressure controls, seeded proof-mode repetitions and positive translation differential evidence. It does **not** close the independent non-SV-COMP external benchmark, full translator equivalence/mutation coverage, all component ablations, Ultimate rejected-input and long-budget fairness reruns, wider comparable baselines, or new LLM sampling/cost studies. The existing nonlinear-verifier boundary remains unchanged.
