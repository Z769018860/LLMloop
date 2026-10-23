int two_phase(int n) {
    int i = 0;
    int p = 0;
    while (i < n) {
        if (p == 0) {
            p = 1;
        } else {
            i = i + 1;
            p = 0;
        }
    }
    return i;
}
