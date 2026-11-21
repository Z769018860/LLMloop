extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = 0;
  while (x < 5000 && __VERIFIER_nondet_int() != 0) {
    if (x < 1) { x = a + a; } else { x = x - y; }
    y = x * 3;
    if (x == 1) { x = x - x; } else { y = x - a; }
  }
  return 0;
}
