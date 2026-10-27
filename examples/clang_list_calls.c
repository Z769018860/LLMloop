#include <stdlib.h>

struct Node { int value; struct Node *next; };

static struct Node *build(int count) {
    struct Node *head = 0;
    for (int i = 0; i < count; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) { return head; }
        p->value = i;
        p->next = head;
        head = p;
    }
    return head;
}

static long long consume(struct Node *head) {
    long long total = 0;
    while (head) {
        struct Node *next = head->next;
        total += head->value;
        free(head);
        head = next;
    }
    return total;
}

long long entry(int n) {
    struct Node *head = build(n);
    return consume(head);
}
