extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 2;
  int y = 0;
  while (y > 0) {
    if (__VERIFIER_nondet_int() != 0) { y = y + 5; } else { x = x + x; }
    if (__VERIFIER_nondet_int() != 0) { y = y * 7; } else { x = y * a; }
    y = y + 7;
  }
  return 0;
}
