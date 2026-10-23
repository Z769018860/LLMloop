# Source projects and reproduction links

Do **not** mistake this repository for a vendor fork of LoopSCC or QCP. The
new finite-control SPath algorithm was independently implemented from the
published conceptual ideas; it makes much narrower claims than the originals.
No third-party source files or pretrained model weights are redistributed.

| Project | Official source or paper | Relation |
|---|---|---|
| LoopSCC (ICSE 2026) | https://anonymous.4open.science/r/LoopSCC-386F/ | Reference method for multi-branch SPath/SCC and oscillation interval; official link published on the ICSE conference page |
| QCP | https://github.com/QinxiangCao/QualifiedCProgramming | Separate C verification and separation-logic tool; optional future verifier |
| MALICE (ICML 2026) | https://proceedings.mlr.press/v306/chen26cm.html | Symbolic traces + LLM invariant-generation research; not vendored |
| LoopSCC paper (earlier version) | https://arxiv.org/abs/2411.02863 | Describes SPath, SPath Graph, SCC contraction and oscillatory intervals |

To reproduce published projects, follow their respective upstream READMEs,
platform-specific build instructions, licenses and versions. QCP has an MIT
license at the linked repository. The conference-hosted LoopSCC anonymous
source URL was verified in the paper's ICSE 2026 listing, but **we could not
access the anonymous source endpoint from this runtime**, so its exact license,
build requirements and code-level behavior have not been independently checked.
Please verify these before copying any upstream implementation into LLMloop.

Current experimental comparison targets include publicly defined looping
examples, but we do not claim performance equivalence to upstream LoopSCC,
QCP, ELBA or MALICE. A proper paper must reproduce each baseline under
comparable language semantics, timeout and hardware conditions.
