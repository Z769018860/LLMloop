#include <stdlib.h>
#include "records.h"
struct Node *make(int);
int consume(struct Node *);
int entry(int n) {
    struct Node *p = make(n);
    if (!p) return -1;
    return consume(p);
}
