extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 0;
  int y = 1;
  while (x != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = a - 2; } else { x = x * 4; }
    if (x > 1) { y = y * a; } else { y = y + y * 3; }
  }
  return 0;
}
