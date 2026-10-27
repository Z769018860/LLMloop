#include <stdlib.h>

struct Node {
    int value;
    struct Node *next;
};

struct Node *entry(int n) {
    struct Node *head = 0;
    for (int i = 0; i < n; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) {
            return head;
        }
        p->value = i;
        p->next = head;
        head = p;
    }
    return head;
}
