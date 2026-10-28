#include <stdlib.h>

struct Node { int value; struct Node *next; };

static struct Node *build(int n) {
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

static struct Node *reverse(struct Node *head) {
    struct Node *prev = 0;
    while (head) {
        struct Node *next = head->next;
        head->next = prev;
        prev = head;
        head = next;
    }
    return prev;
}

struct Node *entry(int n) {
    struct Node *head = build(n);
    head = reverse(head);
    return head;
}
