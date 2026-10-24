long typed_loop(int n) {
    unsigned char byte = 250;
    long total = 0;
    for (int i = 0; i < n; i = i + 1) {
        byte = byte + 1;
        total = total + 1;
    }
    return total + byte;
}
