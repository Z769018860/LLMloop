long typed_memory(int n) {
    unsigned char a[2] = {250, 255};
    unsigned char *p = a;
    long total = 0;
    for (int i = 0; i < n; i = i + 1) {
        p[0] = p[0] + 1;
        p[1] = p[1] + 1;
        total = total + 1;
    }
    return total + a[0] + a[1];
}
