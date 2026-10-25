int *new_values(int n) {
    int *p = calloc(n, sizeof(int));
    if (!p) {
        return 0;
    }
    for (int i = 0; i < n; i++) {
        p[i] = i + 1;
    }
    return p;
}

int *shifted(int *p, int offset) {
    return p + offset;
}

int read_sum(int *p, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += p[i];
    }
    return total;
}

void dispose(int *p) {
    free(p);
}

int calls_heap(int n) {
    int *p = new_values(n);
    if (!p) {
        return -1;
    }
    int *q = shifted(p, 0);
    int result = read_sum(q, n);
    dispose(p);
    return result;
}
