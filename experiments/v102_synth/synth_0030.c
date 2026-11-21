extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 120 || b < 0 || b > 120) return 0;
  int x = b;
  int y = a;
  int z = a;
  while (y > 0) {
    y = y * 3;
    z = a - x;
  }
  return 0;
}
