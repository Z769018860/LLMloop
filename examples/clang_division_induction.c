unsigned entry(unsigned n, unsigned d) {
    const unsigned N = 32;
    unsigned sr = 30;
    if (sr > N - 1) return 0;
    if (sr == N - 1) return n;
    sr++;
    unsigned r = n >> sr;
    n <<= N - sr;
    unsigned carry = 0;
    for (; sr > 0; sr--) {
        r = (r << 1) | (n >> (N - 1));
        n = (n << 1) | carry;
        const int s = (int)(d - r - 1) >> (N - 1);
        carry = s & 1;
        r -= d & s;
    }
    n = (n << 1) | carry;
    return n;
}
