# 参考文献与核验记录 / References, with the check behind each one

**这份文件的每一条都不是凭记忆写的。** 每条的 DOI 走过 Crossref（返回标题、作者、容器、页码），
每条的 arXiv 编号走过 `export.arxiv.org` 的 Atom 接口（返回标题与作者列表），每个 PDF 链接都发过
一次 HTTP Range 请求，记下状态码与 `Content-Type`。**核验时间 2026-11-27。**

核验不是形式：本轮有 **1 个 DOI 与 2 个 arXiv 编号是我记错的**，被上面的检查当场挡下——
`10.1145/512946.512947` 不存在（Cousot & Cousot 1977 的真号是 `10.1145/512950.512973`）、
`2309.09414` 是一篇太阳耀斑论文、`2401.09670` 是 DistServe。**如果按记忆写书目，这三条会带着
正确的格式和错误的身份进稿。** 逐条的复核结论在 `scripts/check_references.py` 里可重跑。

DOI 一律写成 `https://doi.org/<doi>`（可解析到出版方页）；PDF 列**开放副本**，若出版方版本
在订阅墙后，给的是作者/机构托管的那一份，并注明它与正式版的差别。

---

## 1. 不变式推断的经典线 / Invariant inference before LLMs

**[1]** Patrick Cousot, Radhia Cousot. *Abstract interpretation: a unified lattice model for static
analysis of programs by construction or approximation of fixpoints.*
POPL 1977, pp. 238–252. DOI: https://doi.org/10.1145/512950.512973
PDF: https://www.di.ens.fr/~cousot/COUSOTpapers/publications.www/CousotCousot-POPL-77-ACM-p238--252-1977.pdf
（作者主页副本，与 ACM 版同排版 / author-hosted, same typesetting as the ACM version）
核验：Crossref 返回 POPL 1977、作者 Cousot & Cousot；PDF `206 application/pdf`。

**[2]** Cormac Flanagan, K. Rustan M. Leino. *Houdini, an Annotation Assistant for ESC/Java.*
FME 2001 (Formal Methods Europe), LNCS, pp. 500–517.
DOI: https://doi.org/10.1007/3-540-45251-6_29
PDF（开放副本）: https://ftpmirror.your.org/pub/misc/bitsavers/pdf/dec/tech_reports/SRC-TN-2000-003.pdf
（Compaq SRC Technical Note 2000-003，正文与 FME'01 版相同，页码与排版不同 /
the SRC technical-note version; same text, different pagination. 出版方 PDF 在订阅墙后）
核验：Crossref 返回 FME 2001、pp. 500–517；PDF `206 application/pdf`。
**本文的对照族（§4n、§4o）就是这条的候选削弱算法**，区别只在候选的来源。

**[3]** Michael D. Ernst, Jeff H. Perkins, Philip J. Guo, Stephen McCamant, Carlos Pacheco,
Matthew S. Tschantz, Chen Xiao. *The Daikon system for dynamic detection of likely invariants.*
Science of Computer Programming 69(1–3):35–45, 2007.
DOI: https://doi.org/10.1016/j.scico.2007.01.015
PDF: https://homes.cs.washington.edu/~mernst/pubs/daikon-tool-scp2007.pdf
核验：Crossref 返回 SCP 69(1–3)、pp. 35–45、7 位作者；PDF `206 application/pdf`。

**[4]** Pranav Garg, Christof Löding, P. Madhusudan, Daniel Neider. *ICE: A Robust Framework for
Learning Invariants.* CAV 2014, pp. 69–87.
DOI: https://doi.org/10.1007/978-3-319-08867-9_5
PDF: https://link.springer.com/content/pdf/10.1007/978-3-319-08867-9_5.pdf
核验：Crossref 返回 CAV 2014、pp. 69–87；PDF `206 application/pdf`。

## 2. 被比较的工具与见证机制 / The tools, and the witness mechanism

**[5]** Edmund Clarke, Daniel Kroening, Flavio Lerda. *A Tool for Checking ANSI-C Programs.*
TACAS 2004, pp. 168–176. DOI: https://doi.org/10.1007/978-3-540-24730-2_15
PDF: https://link.springer.com/content/pdf/10.1007/978-3-540-24730-2_15.pdf
核验：Crossref 返回 TACAS 2004、pp. 168–176；PDF `206 application/pdf`。

**[6]** Dirk Beyer, M. Erkan Keremoglu. *CPAchecker: A Tool for Configurable Software Verification.*
CAV 2011, pp. 184–190. DOI: https://doi.org/10.1007/978-3-642-22110-1_16
PDF: https://www.sosy-lab.org/research/pub/2011-CAV.CPAchecker_A_Tool_for_Configurable_Software_Verification.pdf
核验：Crossref 返回 CAV 2011、pp. 184–190；PDF `206 application/pdf`。

**[7]** Matthias Heizmann, Jochen Hoenicke, Andreas Podelski. *Software Model Checking for People Who
Love Automata.* CAV 2013, pp. 36–52.
DOI: https://doi.org/10.1007/978-3-642-39799-8_2
PDF: https://link.springer.com/content/pdf/10.1007%2F978-3-642-39799-8_2.pdf
核验：Crossref 返回 CAV 2013、pp. 36–52；PDF `206 application/pdf`。

**[8]** Dirk Beyer, Matthias Dangl, Daniel Dietsch, Matthias Heizmann, Andreas Stahlbauer.
*Witness validation and stepwise testification across software verifiers.*
ESEC/FSE 2015, pp. 721–733. DOI: https://doi.org/10.1145/2786805.2786867
PDF: https://www.sosy-lab.org/research/pub/2015-FSE.Witness_Validation_and_Stepwise_Testification_across_Software_Verifiers.pdf
核验：Crossref 返回 ESEC/FSE 2015、pp. 721–733、**5 位作者**（我原以为 3 位）；PDF `206 application/pdf`。
**§4j 的第三方复核用的是这条定义的见证格式与校验器。**

**[9]** Dirk Beyer. *State of the Art in Software Verification and Witness Validation: SV-COMP 2024.*
TACAS 2024, pp. 299–329. DOI: https://doi.org/10.1007/978-3-031-57256-2_15
PDF: https://link.springer.com/content/pdf/10.1007/978-3-031-57256-2_15.pdf
核验：Crossref 返回 TACAS 2024、pp. 299–329；PDF `206 application/pdf`。

## 3. "不受信提议者 + 受信检查器"这条信任结构 / Untrusted proposer, trusted checker

**[10]** K. Rustan M. Leino. *Dafny: An Automatic Program Verifier for Functional Correctness.*
LPAR-16 2010, LNCS 6355, pp. 348–370.
DOI: https://doi.org/10.1007/978-3-642-17511-4_20
PDF: https://www.microsoft.com/en-us/research/wp-content/uploads/2008/12/dafny_krml203.pdf
核验：Crossref 返回 LPAR 2010、pp. 348–370；PDF `206 application/pdf`。
（auto-active 的先例：注解由人写，工具不改 / annotations written by the user, tool unchanged）

**[11]** Stanislas Polu, Ilya Sutskever. *Generative Language Modeling for Automated Theorem Proving.*
arXiv:2009.03393, 2020. https://arxiv.org/abs/2009.03393
PDF: https://arxiv.org/pdf/2009.03393
核验：arXiv API 返回标题与 2 位作者；PDF `206 application/pdf`。（"模型提议、kernel 判定"的最早形态）

**[12]** Guillaume Lample, Marie-Anne Lachaux, Thibaut Lavril, Xavier Martinet, Amaury Hayat,
Gabriel Ebner, Aurélien Rodriguez, Timothée Lacroix. *HyperTree Proof Search for Neural Theorem
Proving.* NeurIPS 35 (2022), pp. 26337–26349.
DOI: https://doi.org/10.52202/068431-1910 · arXiv:2205.11491 · PDF: https://arxiv.org/pdf/2205.11491
核验：Crossref 返回 "Advances in Neural Information Processing Systems 35"、pp. 26337–26349；
arXiv 页返回 8 位作者；PDF `206 application/pdf`。

## 4. LLM 写规格、写证明 / LLMs writing specifications and proofs

**[13]** Yuhuai Wu, Albert Q. Jiang, Wenda Li, Markus N. Rabe, Charles Staats, Mateja Jamnik,
Christian Szegedy. *Autoformalization with Large Language Models.*
NeurIPS 35 (2022), pp. 32353–32368. DOI: https://doi.org/10.52202/068431-2344
PDF: https://arxiv.org/pdf/2205.12615
核验：Crossref 返回 NeurIPS 35、pp. 32353–32368；arXiv 页返回 7 位作者；PDF `206 application/pdf`。

**[14]** Emily First, Markus N. Rabe, Talia Ringer, Yuriy Brun. *Baldur: Whole-Proof Generation and
Repair with Large Language Models.* ESEC/FSE 2023, pp. 1229–1241.
DOI: https://doi.org/10.1145/3611643.3616243 · PDF: https://arxiv.org/pdf/2303.04910
核验：Crossref 返回 ESEC/FSE 2023、pp. 1229–1241；arXiv 页返回 4 位作者；PDF `206 application/pdf`。

**[15]** Haoze Wu, Clark Barrett, Nina Narodytska. *Lemur: Integrating Large Language Models in
Automated Program Verification.* ICLR 2024.
arXiv:2310.04870 · PDF: https://arxiv.org/pdf/2310.04870
核验：arXiv API 返回 3 位作者、comment 为 "Accepted at ICLR'24"；PDF `206 application/pdf`。
**方法上最近的一条**：它把"LLM + 自动推理器"写成一个有可靠性证明的演算，本文的 §1b 与它是同一个
思路，落到 C 循环的"无 UB"上。

**[16]** Chuyue Sun, Ying Sheng, Oded Padon, Clark Barrett. *Clover: Closed-Loop Verifiable Code
Generation.* AI Verification (AIV 2024), LNCS, pp. 134–155.
DOI: https://doi.org/10.1007/978-3-031-65112-0_7 · PDF: https://arxiv.org/pdf/2310.17807
核验：Crossref 返回容器 "AI Verification"、pp. 134–155、4 位作者；PDF `206 application/pdf`。
（代码/文档/注解三者一致性检查，误接受 0——与本文"零误认证"是同一种主张）

**[17]** Madeline Endres, Sarah Fakhoury, Saikat Chakraborty, Shuvendu K. Lahiri. *Can Large Language
Models Transform Natural Language Intent into Formal Method Postconditions?*
Proc. ACM Softw. Eng. 1(FSE), 2024, pp. 1889–1912.
DOI: https://doi.org/10.1145/3660791 · PDF: https://arxiv.org/pdf/2310.01831
核验：Crossref 返回 PACMSE 1、pp. 1889–1912；arXiv 页返回 4 位作者；PDF `206 application/pdf`。

**[18]** Saikat Chakraborty, Gabriel Ebner, Siddharth Bhat, Sarah Fakhoury, Sakina Fatima,
Shuvendu Lahiri, Nikhil Swamy. *Towards Neural Synthesis for SMT-Assisted Proof-Oriented
Programming.* ICSE 2025, pp. 1755–1767.
DOI: https://doi.org/10.1109/ICSE55347.2025.00002 · PDF: https://arxiv.org/pdf/2405.01787
核验：Crossref 返回 "2025 IEEE/ACM 47th ICSE"、pp. 1755–1767；arXiv 页返回 7 位作者；PDF `206 application/pdf`。

## 5. 大规模"提议—检查"系统 / The propose-then-check systems at scale

**[19]** Trieu H. Trinh, Yuhuai Wu, Quoc V. Le, He He, Thang Luong. *Solving olympiad geometry
without human demonstrations.* Nature 625:476–482, 2024.
DOI: https://doi.org/10.1038/s41586-023-06747-5
PDF: https://www.nature.com/articles/s41586-023-06747-5.pdf
核验：Crossref 返回 Nature 625(7995)、pp. 476–482、5 位作者；PDF `206 application/pdf`。

**[20]** Bernardino Romera-Paredes, Mohammadamin Barekatain, Alexander Novikov, Matej Balog,
M. Pawan Kumar, Emilien Dupont, Francisco J. R. Ruiz, Jordan S. Ellenberg, Pengming Wang,
Omar Fawzi, Pushmeet Kohli, Alhussein Fawzi. *Mathematical discoveries from program search with
large language models.* Nature 625:468–475, 2024.
DOI: https://doi.org/10.1038/s41586-023-06924-6
PDF: https://www.nature.com/articles/s41586-023-06924-6.pdf
核验：Crossref 返回 Nature 625(7995)、pp. 468–475、12 位作者；PDF `206 application/pdf`。

**[21]** Yuri Chervonyi, Trieu H. Trinh, Miroslav Olšák, Xiaomeng Yang, Hoang Nguyen,
Marcelo Menegali, Junehyuk Jung, Junsu Kim, Vikas Verma, Quoc V. Le, Thang Luong.
*Gold-medalist Performance in Solving Olympiad Geometry with AlphaGeometry2.*
arXiv:2502.03544, 2025. PDF: https://arxiv.org/pdf/2502.03544
核验：arXiv API 返回标题与 11 位作者；PDF `206 application/pdf`。

## 6. 最近两年直接做循环不变式的 LLM 工作 / Recent work on loop invariants with LLMs

**[22]** Anjiang Wei, Tianran Sun, Tarun Suresh, Haoze Wu, Ke Wang, Alex Aiken.
*Quokka: Accelerating Program Verification with LLMs via Invariant Synthesis.*
arXiv:2509.21629 (v4, 2026-08), 2025. PDF: https://arxiv.org/pdf/2509.21629
核验：arXiv API 返回标题与 6 位作者；PDF `206 application/pdf`。
（它对每条生成的候选不变式直接问"这条有没有帮上证明"，866 例来自 SV-COMP——与本文"候选只是字符串，
接受与否由验证器决定"的口径一致，但它不设无模型的对照族。）

**[23]** Mostafijur Rahman Akhond, Saikat Chakraborty, Gias Uddin. *LLM For Loop Invariant
Generation and Fixing: How Far Are We?* arXiv:2511.06552, 2025.
PDF: https://arxiv.org/pdf/2511.06552
核验：arXiv API 返回 3 位作者、comment 为 "submitted to the IEEE"；PDF `206 application/pdf`。
（测的是"模型能不能写对"，本文测的是"写对之后有没有净增量"。）

---

## 7. 这 23 条在正文里各自承担什么 / What each cluster does in the argument

| 簇 / cluster | 条数 | 在本文里回答什么 |
| --- | --- | --- |
| 1 不变式推断（[1]–[4]） | 4 | 候选从哪来、怎么被削弱；本文的对照族就是 [2]，不是新发明 |
| 2 工具与见证（[5]–[9]） | 5 | 被比较的三个工具、见证格式、第三方复核的合法性来源（§4j） |
| 3 信任结构（[10]–[12]） | 3 | "提议者不受信、接受者不变"不是本文首创，T2 是它的 C 循环实例 |
| 4 LLM 写规格/证明（[13]–[18]） | 6 | 同一条路上的六个近邻；[15][16] 的主张形状与本文最接近 |
| 5 大规模提议—检查（[19]–[21]） | 3 | 这条路能走多远的上界证据；本文的瓶颈在与它们不同的一侧（覆盖率，§4e） |
| 6 最近的循环不变式（[22][23]） | 2 | 本文与 2025–2026  frontier 的差异：净增量 vs 正确率 |

**没有引用的一条，说明理由。** Necula 的 *Proof-Carrying Code*（POPL 1997,
DOI 10.1145/263699.263712——这个 DOI 核验通过、Crossref 返回 pp. 106–119）没有被列进来：
它的公开 PDF 在本轮尝试的四个地址上分别返回 403/404（CMU 主机对非浏览器客户端返回 403），
**我不能给出一个自己没打开过的链接**。这条的论证位置由 [10]（auto-active，人写注解、工具不改）与
[15]（有可靠性证明的 LLM+推理器演算）承担；补齐它只需要一个可访问的 PDF，不需要改文字。

## 8. 重跑这些检查 / Re-running the checks

```bash
python scripts/check_references.py            # 离线：编号连续、无重复 DOI、正文 [n] 都有条目
python scripts/check_references.py --live     # 在线：每个 PDF 链接发一次 Range 请求，非 PDF 则非零退出
```

`--live` 会打印每条的 `状态码 + Content-Type`；出版方改版会让它变红——那时要修的是链接，不是文字。
