#include "api.h"
int visit(Cell p[]) {
    p[1] += 1;
    return p[0] + p[1];
}
