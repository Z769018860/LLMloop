# Bounded C memory frontend

\`--c-memory\` scalarizes fixed-size \`int\` arrays into cells and models each
pointer as an \`(object_id, offset)\` pair. Copies retain alias identity; loads
and stores become SMT \`ite\` expressions. Dereferences add bounds and lifetime
conditions to path guards. If an access may be invalid, path coverage is not
certified. The frontend accepts one outer \`while\`, initialized scalar locals,
initialized fixed arrays, pointer copies/arithmetic, fixed-size \`calloc\`, and
\`free(pointer)\`.

Nested \`for\` and \`while\` loops inside the outer loop are statically unrolled
up to \`--max-unroll\`; translation fails if exit is not established within
that bound. \`malloc\` and uninitialized arrays are rejected, not assumed to
contain zeros. Successful allocation is assumed. Values use mathematical
integers, not C bit-vector/promotion semantics. General heap allocation,
casts, structs/unions, arbitrary calls, memory accesses in the outer loop
guard, and arbitrary parameter-dependent inner loops remain unsupported.

~~~bash
llmloop-smt examples/c_memory_array.c --c-memory --parameter-bounds '{"n":[0,3]}' --input n=3
llmloop-smt examples/c_memory_pointer_alias.c --c-memory --parameter-bounds '{"n":[0,2]}' --input n=1
~~~
