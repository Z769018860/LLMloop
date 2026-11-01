#include <stdlib.h>
#include "records.h"
struct Node *make(int n) {
    struct Node *p = calloc(1, sizeof(struct Node));
    if (!p) return 0;
    struct Node *q = calloc(1, sizeof(struct Node));
    if (!q) { free(p); return 0; }
    p->value = n;
    p->next = q;
    q->value = n + 1;
    q->next = 0;
    return p;
}
