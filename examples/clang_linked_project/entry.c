#include "interfaces.h"
static int adjust(int value) { return value + ENTRY_STEP; }
int entry(int n) {
    int narrowed = narrow_step(n);
    return helper(n) + adjust(n) + narrowed;
}
