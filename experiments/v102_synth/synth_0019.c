extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 120 || b < 0 || b > 120) return 0;
  int x = 1;
  int y = b;
  int z = 0;
  while (z < 10) {
    z = x * b;
  }
  return 0;
}
