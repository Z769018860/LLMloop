struct Node { int value; struct Node *next; };
struct Node *new_node(int value, struct Node *next) {
    struct Node *node = calloc(1, sizeof(struct Node));
    if (!node) return 0;
    node->value = value;
    node->next = next;
    return node;
}
void dispose_nodes(struct Node *node) {
    while (node) {
        struct Node *next = node->next;
        free(node);
        node = next;
    }
}
int struct_list(int n) {
    struct Node *head = 0;
    for (int i = 0; i < n; i++) {
        struct Node *node = new_node(i + 1, head);
        if (!node) {
            dispose_nodes(head);
            return -1;
        }
        head = node;
    }
    int sum = 0;
    struct Node *cursor = head;
    while (cursor) {
        sum += cursor->value;
        cursor = cursor->next;
    }
    dispose_nodes(head);
    return sum;
}
