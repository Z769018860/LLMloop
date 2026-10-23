int sequential_cfg(int n) {
    int x = 0;
    int i = 0;
    int y = 0;
    while (i < n) {
        if (x < 5) {
            x = x + 2;
        } else {
            x = x - 3;
        }
        if (x >= 4) {
            y = y + 2;
        } else {
            y = y + 1;
        }
        i = i + 1;
    }
    return y;
}
