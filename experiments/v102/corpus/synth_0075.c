extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 2;
  int y = b;
  while (x != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = y * 3; } else { y = x * 2; }
    y = x - y;
    y = x + x * a;
  }
  return 0;
}
