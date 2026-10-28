#include <stdlib.h>

struct Node { int value; struct Node *next; };

long long entry(int n) {
    struct Node *head = 0;
    for (int i = 0; i < n; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) { break; }
        p->value = i;
        p->next = head;
        head = p;
    }
    struct Node *prev = 0;
    while (head) {
        struct Node *next = head->next;
        head->next = prev;
        prev = head;
        head = next;
    }
    head = prev;
    long long total = 0;
    while (head) {
        struct Node *tail = head->next;
        total += head->value;
        free(head);
        head = tail;
    }
    return total;
}
