unsigned int f(unsigned char x, int y) {
    unsigned char z = x;
    z = z + 1;
    if (y < 0) {
        return z;
    }
    return (unsigned int)y + z;
}
