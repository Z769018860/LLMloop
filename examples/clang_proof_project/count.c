#include "config.h"
Counter clang_count(int n) {
    Counter x = 0;
    for (int i = 0; i < n; i++) {
        x += STEP;
    }
    return x;
}
