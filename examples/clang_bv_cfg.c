int entry(int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        if (i == 3) continue;
        sum += i;
        if (i == 5) break;
    }
    return sum;
}
