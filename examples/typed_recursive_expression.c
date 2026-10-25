int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
int recursive_expression(int n) {
    return factorial(n) + 2;
}
