int entry(unsigned int x) {
    return x ? __builtin_clz(x) + __builtin_ctz(x) : 0;
}
