extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 2;
  int y = a;
  while (__VERIFIER_nondet_int() != 0) {
    if (y > 0) { x = y + y; } else { y = y + x * 2; }
    y = b - b;
  }
  return 0;
}
