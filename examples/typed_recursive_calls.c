int *recursive_values(int n) {
    if (n <= 0) {
        return calloc(1, sizeof(int));
    }
    int *p = recursive_values(n - 1);
    if (p) {
        p[0] += n;
    }
    return p;
}

int recursive_heap(int n) {
    int *p = recursive_values(n);
    if (!p) {
        return -1;
    }
    int result = p[0];
    free(p);
    return result;
}
