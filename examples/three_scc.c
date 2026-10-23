int three_scc(int n) {
    int p = 0;
    int i = 0;
    int x = 0;
    int y = 0;
    while (i < n) {
        if (p == 0) {
            x = x + 5;
            p = 1;
        } else if (p == 1) {
            x = x + 1;
            i = i + 1;
            p = 2;
        } else if (p == 2) {
            x = x + 3;
            i = i + 1;
            p = 3;
        } else {
            x = x + 2;
            i = i + 1;
            p = 1;
        }
    }
    return x;
}
