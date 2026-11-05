int entry(int n) {
    if (n < 1 || n > 3) return 0;
    int *p = 0;
    int original[n];
    unsigned char c = 2;
    int narrow[n + sizeof(((void)(n = 0), c))];
    int pointer_size[n + sizeof((p[n++], original)) / sizeof(int *)];
    return n + c + (int)(sizeof(original) + sizeof(narrow) + sizeof(pointer_size));
}
