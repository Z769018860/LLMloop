#include "interfaces.h"
static int adjust(int value) { return value + SUPPORT_STEP; }
Byte narrow_step(Byte value) { return value + 1; }
int helper(int value) { return adjust(value); }
