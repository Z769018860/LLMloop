#include "api.h"
int fill(int *p, int n) {
    p[0] = n;
    p[1] = n + 1;
    p[2] = n + 2;
    return p[0] + p[1] + p[2];
}
