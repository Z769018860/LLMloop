extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = a;
  int y = a;
  while (x != 0) {
    y = a + x;
    if (x < a) { y = x * a; } else { x = x + y; }
  }
  return 0;
}
