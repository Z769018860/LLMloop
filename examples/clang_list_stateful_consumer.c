typedef __SIZE_TYPE__ Size;
void *calloc(Size, Size);
void free(void *);
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

static long long consume(struct Node *q, int seed) {
    long long total = seed;
    long long history = 0;
    while (q) {
        struct Node *tail = q->next;
        total += q->value;
        history += total;
        free(q);
        q = tail;
    }
    return total + history;
}

long long entry(int n, int delta) {
    struct Node *head = build(n);
    return consume(head, delta);
}
