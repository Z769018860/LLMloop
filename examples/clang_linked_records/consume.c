#include <stdlib.h>
#include "records.h"
int consume(struct Node *p) {
    struct Node *q = p->next;
    int result = p->value + q->value;
    free(q);
    free(p);
    return result;
}
