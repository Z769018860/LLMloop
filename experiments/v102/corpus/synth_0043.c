extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = 2;
  while (y > 0) {
    y = x + y;
    if (x > 0) { x = a + 3; } else { y = y + x * 2; }
    x = x + x * 3;
  }
  return 0;
}
