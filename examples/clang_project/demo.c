#include "config.h"
#ifndef BASE
#define BASE 3
#endif
int clang_demo(int n) {
    int values[n + 1];
    values[0] = BASE + STEP;
    Node node = { (unsigned char)n, 0 };
    union Number { int signed_value; unsigned unsigned_value; } number;
    number.signed_value = values[0];
    return node.value + number.signed_value;
}
