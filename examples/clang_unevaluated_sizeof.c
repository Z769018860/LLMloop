int entry(int n) {
    if (n < 1 || n > 3) return 0;
    int *p = 0;
    int original[1];
    int data[n + sizeof(original[n++]) + sizeof(*p) / sizeof(int)];
    int narrow[n + sizeof((unsigned char)(n = 0))];
    return n + (int)(sizeof(data) + sizeof(narrow));
}
