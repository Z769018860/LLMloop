extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = 1;
  int y = 2;
  while (x != 100) {
    x = x + x * 3;
    if (__VERIFIER_nondet_int() != 0) { y = x * 4; } else { x = y - x; }
  }
  return 0;
}
