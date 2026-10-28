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

static long long consume(struct Node *head) {
    long long total = 0;
    while (head) {
        struct Node *tail = head->next;
        total += head->value;
        free(head);
        head = tail;
    }
    return total;
}

static void map_payload(struct Node *cursor, unsigned char delta) {
    while (cursor) {
        cursor->value = cursor->value + delta;
        cursor = cursor->next;
    }
}

long long entry(int n, int delta) {
    struct Node *head = build(n);
    map_payload(head, delta + 260);
    head = reverse(head);
    return consume(head);
}
