int f(int n, int m) {
    int *p = calloc(n * m, sizeof(int));
    int i = 0;
    int j = 0;
    for (i = 0; i < n; i = i + 1) {
        for (j = 0; j < m; j = j + 1) {
            p[i * m + j] = p[i * m + j] + i + j;
        }
    }
    return p[n * m - 1];
}
