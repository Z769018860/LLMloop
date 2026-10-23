int two_phase(int n) {
    int i = 0;
    int p = 0;
    while (i < n) {
        if (p == 0) {
            p = 1 - p;
        } else {
            i = i + 1;
            p = 1 - p;
        }
    }
    return i;
}
