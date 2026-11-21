extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = a;
  int y = 1;
  while (y < 5000 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { y = y + y * 2; } else { x = x * 4; }
    y = y + y * 2;
    y = a - x;
  }
  return 0;
}
