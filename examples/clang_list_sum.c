#include <stdlib.h>

struct Node {
    int value;
    struct Node *next;
};

long long entry(int n) {
    struct Node *head = 0;
    for (int i = 0; i < n; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) {
            break;
        }
        p->value = i;
        p->next = head;
        head = p;
    }
    long long total = 0;
    while (head) {
        struct Node *next = head->next;
        total += head->value;
        free(head);
        head = next;
    }
    return total;
}
