# LLMloop 论文工作稿

现在可以写完整的**研究草稿**，还不能把它描述为“实证结论齐全、可直接投稿”的版本。
本目录已提供 [英文正文](draft.md)、[证据清单](evidence.json)；
[中文缺口与投稿准备度](../docs/PAPER_READINESS.md) 给出下一步优先级。

原先题目为 **LLM-Guided Certified Loop Acceleration via Periodic Invariants and
Compositional State Summaries**。主线是周期/单调混合状态、可验证闭式转换、循环界与
回退、嵌套组合。代价和概率不是本稿主线；不把循环次数直接当作内存访问代价。

正文已写出摘要、动机、语义与证明义务、三个条件正确性论证、组合方法、实现流程、
现有实验、四个 RQ、基线与消融设计、相关工作、有效性威胁和结论。尚未完成的实验
明确作为待验证项，没有虚构 speedup、真实 LLM 增益或外部工具排名。
标题中的 LLM-Guided 暂为设计方向；若不补真实模型实验，应改为不强调 LLM 的标题，
例如 **Certified Loop Acceleration via Typed Periodic Trajectories and
Compositional State Summaries**，而不能仅靠候选重放支持该主张。

数据冻结分层：v0.58 是已提交的回归/数组语法验证基线；v0.43 是选定 compiler-rt
试点；v0.59 是本轮新增候选协调流程的单独实验。不同版本、输入域、ABI 和重复运行
不能相加成独立程序数。这个项目不使用另一个 Eppather/MemPath 项目的程序数或结论。

本稿没有假定投稿会议。正式投稿前需补完整相关工作阅读和方法对比，统一版式、页数、
匿名要求及匿名 artifact；当前工作目录不是已验证的匿名投稿包。
