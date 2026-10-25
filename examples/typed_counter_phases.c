long counter_phases(int n, int threshold) {
    long total = 0;
    for (int i = 0; i < n; i++) {
        total += 3;
        if (i <= threshold) {
            total += 2L * i + 1;
        } else {
            total += 4L * i + 2;
        }
        total -= 1;
    }
    return total;
}
