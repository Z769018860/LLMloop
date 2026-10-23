int sequential_memory_loops(int n) {
    int a[2] = {1, 2};
    int i = 0;
    int j = 0;
    int x = 0;
    while (i < n) {
        x = x + 1;
        i++;
    }
    x = x + 10;
    for (j = 0; j < 2; j++) {
        a[j] = a[j] + x;
    }
    while (i < n + 2) {
        x = x + 2;
        i++;
    }
    return x;
}
