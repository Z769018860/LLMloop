int f(int n) {
    int *p = calloc(n, sizeof(int));
    int *q = p;
    int i = 0;
    p[0] = 1;
    for (i = 1; i < n; i = i + 1) {
        q[i] = p[i - 1] + 2;
    }
    return q[n - 1];
}
