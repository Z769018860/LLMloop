extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 2;
  int y = 2;
  while (y != 100) {
    if (__VERIFIER_nondet_int() != 0) { x = y * 7; } else { x = x * 2; }
  }
  return 0;
}
