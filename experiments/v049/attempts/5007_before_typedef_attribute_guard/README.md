# Superseded direct-attribute checkpoint

The original 2276-test run and native records are retained unchanged. This checkpoint is not release acceptance: ignored_typedef_attribute.json shows a typedef-hidden alignment promise incorrectly certified while Clang emits an alignment-assumption sanitizer check. Final source retains typedef attribute metadata, checks used alias chains and adds deterministic direct/typedef native trap controls. The final frozen source is validated afresh.
