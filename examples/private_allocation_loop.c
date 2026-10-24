int f(int n) {
    int x = 0;
    int i = 0;
    for (i = 0; i < n; i = i + 1) {
        int *p = calloc(2, sizeof(int));
        int *q = p;
        p[0] = i + 1;
        q[1] = p[0] + 2;
        x = x + q[1];
        free(q);
    }
    return x;
}
