int pointer_alias(int n) {
    int a[2] = {4, 9};
    int *p = &a[1];
    int *q = p;
    int x = 0;
    int i = 0;
    while (i < n) {
        *q = *p + 1;
        x = *q;
        i++;
    }
    return x;
}
