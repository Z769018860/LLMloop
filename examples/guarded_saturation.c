int saturation(int steps, int limit) {
    int x = 0;
    for (int i = 0; i < steps; i = i + 1) {
        if (x < limit) {
            x = x + 1;
        } else {
            x = x;
        }
    }
    return x;
}
