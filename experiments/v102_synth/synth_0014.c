extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 120 || b < 0 || b > 120) return 0;
  int x = 0;
  int y = a;
  while (y < 100) {
    if (__VERIFIER_nondet_int() != 0) { y = b - a; } else { y = b - b; }
    x = x + y * 3;
    x = y + y * a;
  }
  return 0;
}
