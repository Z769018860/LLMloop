extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = b;
  int y = a;
  while (x > 0) {
    if (__VERIFIER_nondet_int() != 0) { y = y + 46341; } else { y = x - b; }
    x = x - y;
    y = y * a;
  }
  return 0;
}
