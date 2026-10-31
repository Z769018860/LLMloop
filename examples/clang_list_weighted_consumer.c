#include <stdlib.h>

struct Node { int value; struct Node *next; };

struct Node *build(int n) {
    struct Node *head = 0;
    for (int i = 0; i < n; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) { return head; }
        p->value = i;
        p->next = head;
        head = p;
    }
    return head;
}

long long consume(struct Node *head, unsigned char weight, int offset) {
    long long total = 0;
    while (head) {
        struct Node *next = head->next;
        total += (long long)head->value * weight + offset;
        free(head);
        head = next;
    }
    return total + weight;
}

long long entry(int n, int delta) {
    struct Node *head = build(n);
    return consume(head, delta + 260, delta - 1);
}
