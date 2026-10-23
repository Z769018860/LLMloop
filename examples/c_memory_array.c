int array_update(int n) {
    int a[3] = {1, 2, 3};
    int i = 0;
    int x = 0;
    while (i < n) {
        a[i] = a[i] + 1;
        x = a[i];
        i++;
    }
    return x;
}
