extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 250) return 0;
  int x = 1;
  int y = 2;
  while (y > 0) {
    if (x != 1) { y = a + x; } else { x = x + x * 3; }
    if (x > 1) { y = y + x * 2; } else { y = a - a; }
  }
  return 0;
}
