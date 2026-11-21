extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 120 || b < 0 || b > 120) return 0;
  int x = 0;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    y = x + a;
    x = b + y;
    if (y == b) { x = b - 7; } else { x = y - y; }
  }
  return 0;
}
