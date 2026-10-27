#include <stdlib.h>

struct Node {
    long value;
    struct Node *next;
};

struct Node *make(long value) {
    struct Node *p = calloc(1, sizeof(struct Node));
    if (!p) {
        return 0;
    }
    p->value = value;
    p->next = 0;
    return p;
}

long entry(int n) {
    struct Node *head = make(n);
    if (!head) {
        return -1;
    }
    struct Node *tail = make(n + 1);
    if (!tail) {
        free(head);
        return -2;
    }
    head->next = tail;
    struct Node *next = head->next;
    long result = head->value + next->value;
    free(tail);
    free(head);
    return result;
}
