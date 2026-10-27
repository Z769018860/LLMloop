#include <stdlib.h>

struct Node { int value; struct Node *next; };

static struct Node *build(int count) {
    struct Node *head = 0;
    for (int i = 0; i < count; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) { break; }
        p->value = i;
        p->next = head;
        head = p;
    }
    return head;
}

struct Node *entry(int n) {
    struct Node *head = build(n);
    return head;
}
