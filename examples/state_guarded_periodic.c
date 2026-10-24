int alternating(int n, int a) {
    int sign = 1;
    int total = a;
    for (int i = 0; i < n; i = i + 1) {
        if (sign > 0) {
            total = total + sign;
            sign = -sign;
        } else {
            total = total + 2 * sign;
            sign = -sign;
        }
    }
    return total;
}
