int f(void) {
    int x = 2147483647;
    int i = 0;
    while (i < 1) {
        x = (x + 1) - 1;
        i++;
    }
    return x;
}
