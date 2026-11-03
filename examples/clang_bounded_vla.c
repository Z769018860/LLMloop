static int fill(int *p, int n) {
    for (int i = 0; i < n; ++i) {
        p[i] = i + 1;
    }
    return p[n - 1];
}

int entry(int n) {
    if (n < 1 || n > 8) return 0;
    int values[n];
    int last = fill(values, n);
    n = 1;
    return last + (int)sizeof(values);
}
