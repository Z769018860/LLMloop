extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = a;
  int y = b;
  while (x != 100) {
    y = b - y;
    if (y == b) { y = x + a; } else { y = b - 1; }
  }
  return 0;
}
