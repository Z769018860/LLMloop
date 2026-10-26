#include <stdlib.h>
typedef struct Node Node;
struct Node { int value; Node *next; };

Node *build(int n) {
    Node *head = NULL;
    for (int i = 0; i < n; i++) {
        Node *node = malloc(sizeof(Node));
        if (!node) { return head; }
        node->value = i;
        node->next = head;
        head = node;
    }
    return head;
}

long long entry(int n) {
    Node *head = build(n);
    long long sum = 0;
    while (head) {
        Node *next = head->next;
        sum += head->value;
        free(head);
        head = next;
    }
    return sum;
}
