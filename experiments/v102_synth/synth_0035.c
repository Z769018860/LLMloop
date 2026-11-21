extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = a;
  int y = 0;
  while (y != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = x * 4; } else { x = y - a; }
  }
  return 0;
}
