int f(int n, int m) {
    int a[2] = {1, 7};
    int *p = &a[0];
    int *q = p;
    int i = 0;
    int j = 0;
    for (i = 0; i < n; i = i + 1) {
        for (j = 0; j < m; j = j + 1) {
            *p = *q + 1;
        }
        *q = *q * 2;
        a[1] = a[1] + a[0];
    }
    return a[1];
}
