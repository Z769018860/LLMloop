# 证明规则的可靠性 / Soundness of the proof rule

**这份文档是什么。** 审计 §6 的 E5：把 `houdini_loops` 用的证明规则写成**推理规则**，并给出
**可靠性定理**。缺了它，CAV/TACAS 正刊基本不可能——现在有了，但要对准它说的话：
**定理只覆盖核心规则与它的实现义务；两条假设（前端翻译忠实、SMT 求解器可靠）单独列出，
并说明各自被什么实验检验。** 不覆盖终止性、不覆盖堆/指针（那些被前端拒收在片段之外）。

**What this document is.** The inference rule behind `houdini_loops`, its obligation list as the
implementation emits it, and a soundness theorem: *if every obligation is valid, no execution of the
fragment program reaches undefined behaviour* — plus a second theorem that says the answer does not
depend on who proposed the invariants. Two hypotheses (faithful front-end translation, sound SMT
solver) are stated separately with the experiment that tests each. Termination and heap are outside
the fragment and outside the claim.

---

## 0. 结论先行 / The three statements

| # | 命题 | 一句话 |
| --- | --- | --- |
| T1 | **可靠性**：若八类义务全部valid，则从参数域内任何初始状态出发，任何有限执行都不经过未定义行为 | 归纳法，见 §5 |
| T2 | **提议者无关**：证明规则只检查候选不变式；采样、Houdini 削弱、LLM 提议只决定"找到什么"，不决定"接受什么" | 一段话，见 §6 |
| T3 | **条件性**：T1 依赖两条假设 H1（前端翻译忠实）与 H2（求解器可靠）；H2 已被 E1 的第三方复核在 121 条不变式上检验，H1 只能差分测试 | 见 §7 |

T2 是这篇工作真正的卖点，而且它现在是**定理而不是宣传语**：LLM 提议错了只会让证明失败
（完备性损失），不会让错误的程序被接受（可靠性不受影响）。§4.2 的消融因此可以被正确解读为
**完备性消融**，而不是可靠性消融。

---

## 1. 片段 / The fragment

程序 $P$ 是单个函数 $f(\vec{p})\ \{\ S;\ \texttt{return}\ e;\ \}$，其中：

* 参数与局部变量是标量（有符号/无符号 `char`/`short`/`int`/`long`/`long long`，`_Bool`），
  无指针、无数组、无结构体、无堆——这些由前端拒收，不进入本定理的论域；
* 语句 $S$：赋值 `x = e`、`if (b) S else S`、`while (b) S`（`for` 先脱糖）、复合、`skip`；
* 循环体里不允许 `break` / `continue` / `return` / `goto` / 声明 / `do-while`（`typed_invariant_loops.py:65`），
  循环 1..8 个（`:60`）；
* `unknown()`（或任何 nondet 调用）被重写成一个**新输入**，在其类型范围内全称量化
  （`_rewrite_calls`，`typed_invariant_while.py:38`；范围见 `_nd_range`，`:222`）。

这些限制不是"实现方便"，而是**义务能被逐语句写出**的前提：有了它们，符号执行对每条语句只有
有限多个出口，路径条件可以枚举，覆盖率义务（§4 的 O7）才有意义。

---

## 2. 语义 / Semantics

**值域。** 类型 $\tau$ 的值域是 $[\min_\tau, \max_\tau]$（无符号为 $[0, 2^w-1]$）。
状态 $\sigma$ 是从变量到值的映射，$\sigma \models D$ 表示每个参数落在其声明类型的值域内
（`self.domain`，`typed_recurrence.py:50`；若程序自身的 `assume` 收窄了范围，$D$ 取收窄后的交）。

**表达式的三值求值。** 我们对每个表达式 $e$ 定义两件事：

$$\llbracket e \rrbracket \sigma \in \mathrm{Val} \qquad \text{与} \qquad \sigma \models \mathsf{safe}(e)$$

即"值是多少"和"求值是否未定义"。$\mathsf{safe}$ 与实现里的 `TypedTerm.safe`
（`symbolic_integers.py`）逐条对应：

| 构造 | 未定义的条件 |
| --- | --- |
| 有符号加法/减法/乘法 $a \circ b$ | 精确结果越出 $\tau$ 的值域（`symbolic_integers.py:113`） |
| 除法/取模 $a / b$ | $b = 0$，或 $a = \min_\tau \wedge b = -1$（`:116`） |
| 移位 $a \ll b$, $a \gg b$ | $b < 0$ 或 $b \ge w$（`:98`） |
| 一元负号 $-a$（有符号） | $a = \min_\tau$（`:85`） |
| `&&` / `\|\|` | 左操作数未定义，或（左侧选中右侧时）右操作数未定义（`:94`）——短路语义 |
| 条件 $c\,?\,a\,:\,b$ | $c$ 未定义，或选中分支未定义（`:78`） |
| 读变量 / 常量 | 从不已定义失败 |

**小步语义。** $\langle \sigma, s \rangle \to \langle \sigma', s' \rangle$，以及三类终态：
$\langle \sigma, \texttt{skip}\rangle$（正常结束）、$\mathsf{wrong}$（未定义行为）、$\Uparrow$（发散）。
规则是标准的：赋值要求 $\sigma \models \mathsf{safe}(e)$ 否则 $\mathsf{wrong}$；条件语句要求守卫未定义
则 $\mathsf{wrong}$；`while` 每次判守卫同理。nondet 输入每步可任取范围内的值（关系式，不是函数）。

**本文说的"安全"**：从 $\sigma_0 \models D$ 出发的任何**有限**执行前缀都不经过 $\mathsf{wrong}$。
我们把发散排除在主张之外，因此这是"部分正确性 + 无未定义行为"，而不是全正确性。

---

## 3. 推理规则 / The rule

设程序有 $n$ 个循环 $L_1 \dots L_n$（源序），循环 $k$ 的守卫为 $b_k$、体为 $B_k$，
不变式 $I_k$ 是关于"循环状态变量"（参数 + 第一个循环前声明的局部 + 循环中被赋值的局部）的公式。
记 $\mathsf{ND}$ 为所有 nondet 输入的类型范围约束，$\mathsf{rg}(\sigma)$ 为状态变量落在各自类型值域内。

规则 **INV** 有八类前提（编号与实现中的 obligation 标签一一对应，见 §4 的表）：

$$\frac{
\begin{array}{ll}
\textbf{(O1)}\ D \Rightarrow \bigwedge \mathsf{safe}(\text{循环前的语句}) &
\textbf{(O2)}\ \forall \varphi \in \Phi_k:\ D \wedge g_\varphi \Rightarrow I_k(\sigma_\varphi)\\
\textbf{(O3)}\ D \wedge \mathsf{rg} \wedge \mathsf{ND} \wedge I_k \Rightarrow \mathsf{safe}(b_k) &
\textbf{(O4)}\ \forall \varphi \in \Phi^{B}_k:\ D \wedge \mathsf{rg} \wedge \mathsf{ND} \wedge I_k \wedge b_k \wedge g_\varphi \Rightarrow I_k(\sigma'_\varphi)\\
\textbf{(O5)}\ D \wedge \mathsf{rg} \wedge \mathsf{ND} \wedge I_k \Rightarrow \mathsf{safe}(b_k) \text{（出口处同一义务）} &
\textbf{(O6)}\ D \wedge \mathsf{rg} \wedge \mathsf{ND} \wedge I_n \wedge \neg b_n \Rightarrow \bigwedge \mathsf{safe}(\text{循环后的语句}) \wedge \mathsf{safe}(e_{\text{ret}})\\
\textbf{(O7)}\ \text{覆盖：}\ \mathit{pre} \wedge g \Rightarrow \bigvee_{\varphi} g_\varphi \text{（每个语句段的出口路径覆盖入口）} &
\textbf{(O8)}\ I_k \text{ 是良构公式（每循环 1..256 条原子）}
\end{array}}{\vdash \{I_1 \dots I_n\}\ P \text{ 安全}}$$

其中 $\Phi_k$ 是到达循环 $k$ 入口的符号路径集合（可能来自循环前的代码、上一个循环的出口、
或外层循环体），$\Phi^B_k$ 是执行完 $B_k$ 的符号路径集合，$g_\varphi$ 是路径条件，
$\sigma_\varphi$ / $\sigma'_\varphi$ 是路径上的符号状态。**O6 对每个循环都成立**——因为每个循环的出口
都可能接后续语句，实现里把"循环后的语句"作为普通语句段处理，义务因此在各层循环上重复出现。

**读法**：前提里没有"程序终止"这一条。规则说的是"每一步都不出错、且不变式在循环头成立"；
发散不违反它。

---

## 4. 规则与实现的对应 / The implementation emits exactly these

| 义务 | 实现位置 | 形式 |
| --- | --- | --- |
| O1 初始化已定义 | `typed_invariant_loops.py:68` `'initialization defined'` | `check(D, ⋀ obligations)` |
| O2 入口成立 | `:101` `'loop k: invariant at entry (path φ)'` | `check(premise ∧ g ∧ extra, I_k)` |
| O3 守卫已定义 | `:107` `'loop k: loop condition defined'` | `check(pre ∧ ND ∧ rg ∧ I_k, safe(b_k))` |
| O4 保持 | `:112` `'loop k: invariant preserved (body path φ)'` | `check(pre_b ∧ extra ∧ g, I_k[post])` |
| O5 出口守卫已定义 | `:115` `'loop k: exit loop condition defined'` | 同 O3 |
| O6 返回表达式已定义 | `:76` `'return expression defined (path φ)'` | `check(premise ∧ extra ∧ g, safe(e_ret))` |
| O6' 语句段操作已定义 | `typed_invariant_tree.py:195` `'operations defined'` | `check(premise ∧ extra, ⋀ obligations)` |
| O7 路径覆盖 | `typed_invariant_tree.py:196` `'paths cover entry'` | `check(premise ∧ extra ∧ g, ⋁ g')` |
| 判定方式 | `typed_recurrence.py:58` `check` | `premise ∧ ¬claim` UNSAT |

`check` 的实现就是 $\mathsf{premise} \wedge \neg\mathsf{claim}$ 不可满足性——没有"近似"，
没有超时当作成功（超时会抛 `ProofFailure`，见同一函数）。

一条额外的证明通道：标签以 ` range` 结尾的义务可以先由**有理区间证书**
（`interval_certificate.py`）兜住，它只在前提的合取项上做精确有理区间传播，
不评估任何源操作、不假设任何表达式已定义（文件首行注释即是这个约定）。它只被用于范围类义务，
从不用于 $\mathsf{safe}$ 义务——这一点在代码里由标签过滤保证。

---

## 5. 定理与证明 / Theorem and proof

**定理 T1（可靠性）。** 设 $P$ 是 §1 的片段程序，$I_1 \dots I_n$ 是任意公式组（**不问来历**）。
若 O1–O7 全部valid（每条都是 `premise ∧ ¬claim` 不可满足），则对任意 $\sigma_0 \models D$，
任意有限执行 $\langle \sigma_0, P\rangle \to^* \langle \sigma, s\rangle$ 都有 $\sigma \ne \mathsf{wrong}$；
并且在每个循环头，对应的 $I_k$ 成立。

**证明。** 先证一个关于语句段的引理，再对执行步数归纳。

*引理（符号执行是过近似）。* 固定 `premise`。设 $\mathsf{SE}(s, \mathit{pre}, g, \sigma)$ 返回有限集
$\{(g_i, \sigma_i, o_i)\}$，其中 $o_i$ 是该路径上收集到的定义性义务的合取，且满足
O7（$\mathit{pre} \wedge g \Rightarrow \bigvee_i g_i$）与 O6'（$\mathit{pre} \wedge g \Rightarrow \bigwedge_i o_i$）。
则对任何具体状态 $\sigma_0$ 满足 $\mathit{pre} \wedge g$，任何 $s$ 的终止执行都到达某个 $\sigma'$
满足 $g_i$ 且 $\sigma'$ 与 $\sigma_i$ 在这些变量上取值一致。

对 $s$ 的结构归纳：赋值时 $\sigma_i$ 就是把 $\llbracket e\rrbracket\sigma$ 写进变量，$o_i = \mathsf{safe}(e)$；
`if` 时按守卫取值分成两支，O7 保证两支的守卫互斥且穷尽（守卫已定义由 $o_i$ 给）；复合语句逐句串接。
归纳假设保证子段的过近似性，串接保持。

*主证明。* 对执行步数归纳，强化不变式为：

> **(†)** 在配置 $\langle \sigma, s\rangle$ 中，$\sigma$ 已定义（不等于 $\mathsf{wrong}$），
> 且若 $s$ 是某循环 $L_k$ 的守卫判定，则 $I_k$ 在 $\sigma$ 上成立。

初始：$\sigma_0 \models D$，循环前段由 O1 与引理给出已定义；第一次到达 $L_k$ 的守卫时由 O2 给出 $I_k$。

归纳步，按 $s$ 的形状：

* 循环前的普通语句段：定义性由 O6' 与引理给出，$I$ 未涉及。
* 循环 $L_k$ 判守卫：由 O3，$\mathsf{safe}(b_k)$ 成立，故下一步不是 $\mathsf{wrong}$；
  若 $b_k$ 假，进入出口，由 O5 与 O6 保证后续段与返回表达式已定义，出口状态是
  "任意满足 $I_k \wedge \neg b_k$ 的类型内状态"——这正是规则允许后继代码假设的全部；
  若 $b_k$ 真，进入 $B_k$。
* 循环体 $B_k$：对体内每个语句段用引理；到达体内嵌套循环 $L_j$ 时用 O2（$L_j$ 的入口路径来自
  $I_k \wedge b_k$），出体后由 O4 得 $I_k$ 重新成立，回到守卫判定，满足 (†)。

（†）对每一步成立，故任何有限前缀都不含 $\mathsf{wrong}$，且循环头不变式成立。∎

**推论 T1'（证书语义）。** 在上述前提下，$I_k$ 是循环 $L_k$ 的**归纳不变式**：入口处成立、
被体保持、且在 $I_k \wedge b_k$ 下体与守卫都已定义。E1 交第三方验证器复核的正是这三件事
（SV-COMP 见证的 `loop_invariant` 语义），因此 T1 与 E1 说的是同一件事的两个侧面：
T1 说"若我们自己的检查器说 valid，则程序安全"，E1 说"我们的检查器说是 inductive 的东西，
别人的检查器也说是 inductive"。

---

## 6. 定理 T2：提议者无关 / The answer does not depend on the proposer

**定理 T2。** 设 $\mathcal{A}$ 是任意过程，输出一组候选公式 $I = \mathcal{A}(P)$；
`analyze_request` 对 $I$ 跑 §4 的义务，只有在全部valid 时才报告 `PROVED`。
则对任意 $\mathcal{A}$（包括采样器、Houdini 削弱、LLM、任意恶意提议），
"报告 `PROVED`"$\Rightarrow$ T1 的结论。

**证明。** T1 的前提是"I 的义务全部valid"，与 I 的来源无关；实现里 `houdini_loops` 只在
`r['status'].startswith('PROVED')`（`houdini_loops.py:98`）时返回 `PROVED`，而 `r` 来自
`analyze_request`。提议者只能改变 `cands`（候选集），它进入检查器的唯一通道是
`range_invariants` 参数。因此 $\mathcal{A}$ 的任意错误只可能让检查失败（`STUCK` / `EMPTY` /
`MAX_ROUNDS`），不可能让检查通过。∎

**三个具体推论，都对应代码里一处"看起来像作弊"的地方：**

1. **`CAP = 256` 截断**（`houdini_loops.py:54`）：截断只丢弃候选，故只损失完备性。
2. **`_lean` 与 `_prio` 的重排**（`:46`、`:60`）：只改变尝试顺序，不影响被接受的集合。
3. **60 次采样的原子生成**（`:84`）：采样是"猜到什么"的启发式；它生成的原子若不 inductive，
   会被 O2/O4 拒绝。采样永远不是证明手段——**这一点在论文里必须明说**，否则读者会以为
   我们在"用测试证明"。

因此 §4.2 的 LLM/确定性消融、§4.1 的 165/400 例对照，度量的都是**完备性**：
在不同提议者下能证出多少，而不是"能不能证错"。

---

## 7. 两条假设 / The two hypotheses, and what tests them

| 假设 | 内容 | 被什么检验 | 现状 |
| --- | --- | --- | --- |
| **H1 前端忠实** | `svcomp_translate.py` 把 SV-COMP 源文本改写成片段程序时，保持未定义行为语义（宏展开、`assume` 前置条件、`assert` 处理、整数宽度） | 差分测试（`v103-transdiff`）；E1 的见证在**翻译后**的程序上被判 inductive | 有差分测试，无证明。E1 的零驳回说明"翻译后的程序上不变式确实 inductive"，**不**说明翻译保持了原程序语义 |
| **H2 求解器可靠** | z3 报 `unsat` 时公式真的不可满足 | E1：121 条不变式由 CPAchecker 4.2.2 与 Ultimate 0.3.2 独立复核，**零驳回**；两者与我们的 VC 生成器无共享代码 | 强证据，非证明。注意方向：求解器**假 sat** 只损失完备性（我们据此削弱候选），**假 unsat** 才会不健全——E1 检验的正是后者 |

**H2 为什么能被 E1 检验。** E1 把 $I_k$ 导出成 SV-COMP 见证，交给两个独立验证器在**同一个
C 程序**上重放。验证器要成立，必须自己证明 $I_k$ inductive（入口、保持、守卫已定义）。
如果我们的 VC 编码有错（把不 inductive 的当成 inductive），验证器会驳回。121 条零驳回，
是对 H1∩H2 的一次**独立采样检验**，样本量是 121 条不变式、90 个程序、两个验证器。

---

## 8. 不证明什么 / What is not proved

* **终止性**：规则不含 ranking function 义务（`termination = False`，`typed_invariant_loops.py:43`）。
  因此"无未定义行为"是关于**有限前缀**的；发散的执行不违反定理。
* **堆与指针**：片段之外，前端拒收。E3 的 2085 个工业循环函数里 2067 个正是死在这里。
* **参数域之外的输入**：$D$ 是参数类型值域（或被 `assume` 收窄后的交）。定理对 $D$ 内的一切成立，
  对 $D$ 外的输入不作断言——这不是弱点，是 C 的类型系统本身给的边界，但必须在论文里写清。
* **浮点**：`loop-floats-scientific-comp` 这类语料不在片段内；"整数模型 = 位精确"这句话只对整数成立。
* **前端翻译本身**（H1）：见 §7。
* **多函数**：片段是单函数；跨函数的可靠性要靠 `typed_cfg_calls` 的另一套义务，不在本文定理内。

---

## 9. 与论文的接口 / How this plugs into the paper

* §3（方法）用 §3 的规则替换现在的散文描述；§4 的表直接作为"我们检查了什么"。
* §5（威胁）现在可以写成两条**具名假设**而不是"可能有 bug"：H1 无证明、H2 有独立采样检验。
* §4.2 的消融引用 T2，一句话说清"提议者无关，因此消融只度量完备性"。
* E1（§4j）引用 T1'：第三方复核的对象与定理的结论是同一组义务。

**还剩什么才能真正投 CAV/TACAS。** 本文的定理是**纸面证明 + 实现对应表**，不是机器检验的。
审稿人若要求 Coq/Isabelle，那是另一个量级的工作（把 8 类义务与 §2 的语义在证明助手里形式化）。
在这之前，诚实的说法是："我们给出了规则与证明，并给出了与实现的逐行对应；
H2 被独立验证器在 121 条不变式上检验过，H1 没有证明。"
