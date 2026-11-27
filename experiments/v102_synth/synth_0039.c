extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 120) return 0;
  int x = 1;
  int y = 1;
  int z = 1;
  while (x < a) {
    x = a + 7;
    if (x != a) { x = x - a; } else { y = z + x * 3; }
    x = z * a;
  }
  return 0;
}
