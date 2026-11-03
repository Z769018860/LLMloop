static int advance(int m) {
    return m - 1;
}

int entry(int n) {
    if (n < 1 || n > 3) return 0;
    int total = 0;
    for (int m = n; m > 0; m = advance(m)) {
        int values[m];
        values[m - 1] = m;
        total += (int)sizeof(values) + values[m - 1];
        if (m > 1) continue;
    }
    return total;
}
