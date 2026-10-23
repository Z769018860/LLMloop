int alternating(int n) {
    int i = 0;
    int p = 0;
    int x = 0;
    while (i < n) {
        if (p == 0) {
            x = x + 1;
        } else {
            x = x + 3;
        }
        p = 1 - p;
        i = i + 1;
    }
    return x;
}
