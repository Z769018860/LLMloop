extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = a;
  while (y < 100) {
    if (__VERIFIER_nondet_int() != 0) { x = y * 3; } else { y = y + y; }
    x = y * a;
  }
  return 0;
}
