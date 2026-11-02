#include "api.h"
int entry(int n) {
    Cell a[2] = {n, n + 1};
    return visit(a);
}
