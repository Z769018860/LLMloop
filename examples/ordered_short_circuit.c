int f(void) {
    int x = 2147483647;
    int i = 0;
    while (i < 1) {
        if (0 && x + 1) {
            x = 1;
        } else {
            x = 1 ? 4 : x + 1;
        }
        i++;
    }
    return x;
}
