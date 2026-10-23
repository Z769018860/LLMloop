# LoopSCC public GitHub sources and reproduction

**LoopSCC does have public GitHub source code.** Verified via GitHub's
contents API:

- https://github.com/hahaleyile/LoopSCC (master branch)
- https://github.com/the-elves/LoopSCC (public copy)
- https://github.com/smallzhong/LoopSCC (public copy)

All three copies share README blob SHA dc8a4776260ac00784cff5dbef755af3db88c530.
The first repository includes cfg.py, spath_graph.py, summarizer.py,
recurrence.py, int.py and extensive experiments/exp1 assets.

The ICSE 2026 conference page also links
https://anonymous.4open.science/r/LoopSCC-386F/ .
The identities of the GitHub owners and relationship to the original
anonymous artifact were not conclusively confirmed.

## Reproduction (do NOT copy upstream source into LLMloop)

On a computer with Python 3.12, network and Git:

~~~bash
git clone https://github.com/hahaleyile/LoopSCC.git external/LoopSCC
python3.12 -m venv external/loopscc-venv
source external/loopscc-venv/bin/activate
python -m pip install -r external/LoopSCC/requirements.txt
cd external/LoopSCC
PYTHONPATH=. python experiments/exp1/LoopSCC/input/speed_pldi09_fig1.py
~~~

The upstream requirements pin sympy==1.12.1 and z3-solver==4.13.0.0.
On Windows use Scripts/activate for the venv.

The upstream README describes INT.define_int, CFG.define_loop,
SPath_Graph, Summarizer.summarize and solve/solver_check_trace/check_after_loop.
Its spath_graph.py checks SPath jumps by satisfiable Z3 conditions, then
computes strongly connected components.

**License caution:** the inspected GitHub tree has no root LICENSE file.
Public accessibility is NOT equivalent to a license permitting redistribution.
Do not vendor upstream code without obtaining clarification/permission.
This project provides independent algorithms, not upstream copies.

## Related independently implemented modules

- graph.py: fixed finite-control SPath graph with Tarjan SCCs.
- oscillation.py: data-dependent two-branch oscillation with exact interval
  and modular closed-form acceleration, plus monotone exit bounds.
- oscillation_c.py: small restricted C-to-oscillation translator.

See OSCILLATION.md for mathematical derivations and scope. None of these
is a complete reproduction of the original LoopSCC, QCP or MALICE.
