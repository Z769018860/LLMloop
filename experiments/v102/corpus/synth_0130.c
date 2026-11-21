extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 0;
  int y = a;
  while (y < 1000) {
    x = y * b;
    x = x + y * 3;
    if (y != a) { x = y * 2; } else { y = b + a; }
  }
  return 0;
}
