extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = b;
  int y = 1;
  while (y < 10) {
    if (y != a) { x = x * 2; } else { y = x * 4; }
  }
  return 0;
}
