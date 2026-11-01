typedef __SIZE_TYPE__ Size;
void *calloc(Size, Size);
void free(void *);

struct Node { int value; struct Node *next; };

static struct Node *build(int count, unsigned char bias) {
    struct Node *head = 0;
    for (int i = 0; i < count; i++) {
        struct Node *p = calloc(1, sizeof(struct Node));
        if (!p) { return head; }
        p->value = i + bias;
        p->next = head;
        head = p;
    }
    return head;
}

long long entry(int n, int delta) {
    struct Node *head = build(n + 1, delta + 260);
    long long total = 0;
    while (head) {
        struct Node *tail = head->next;
        total += head->value;
        free(head);
        head = tail;
    }
    return total;
}
