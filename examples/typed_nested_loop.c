long nested_typed(int n, int m) {
    unsigned char byte = 0;
    long total = 0;
    for (int i = 0; i < n; i = i + 1) {
        total = total + 1;
        for (int j = 0; j < m; j = j + 1) {
            byte = byte + 1;
            total = total + 1;
        }
        total = total + 2;
    }
    return total + byte;
}
