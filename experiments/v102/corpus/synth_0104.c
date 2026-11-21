extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 2;
  int y = 2;
  while (y < 50 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = y * a; } else { x = y - 2; }
    if (x < a) { x = y - a; } else { y = y + x * 2; }
  }
  return 0;
}
