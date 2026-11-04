int entry(int n) {
    if (n < 1 || n > 3) return 0;
    int original[n];
    n = 7;
    int copy[sizeof(original) / sizeof(int)];
    int last = (int)(sizeof(copy) / sizeof(int)) - 1;
    copy[last] = last + 1;
    return copy[last] + (int)(sizeof(original) + sizeof(copy));
}
