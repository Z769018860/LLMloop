int cell_value(int x) { return x + 1; }

int entry(int n) {
    if (n < 1 || n > 3) return 0;
    int extra = 1;
    int last = n;
    int values[(unsigned)n + extra];
    int value = cell_value(n);
    values[last] = value;
    extra = 7;
    n = 1;
    return values[last] + (int)sizeof(values);
}
