long coupled_rotate(int n) {
    long x = 1;
    long y = 2;
    long total = 0;
    for (int i = 0; i < n; i++) {
        long temp = x;
        x = -y;
        y = temp;
        total += x;
    }
    return total;
}
