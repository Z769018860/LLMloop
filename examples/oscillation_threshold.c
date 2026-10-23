int oscillation_threshold(int n) {
    int x = 0;
    int i = 0;
    int y = 0;
    while (i < n) {
        if (x < 5) {
            x = x + 2;
            i = i + 3;
            y = y + 1;
        } else {
            x = x - 5;
            i = i + 4;
            y = y + 2;
        }
    }
    return y;
}
