extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = 1;
  int y = 2;
  int z = b;
  while (x != 100) {
    x = x * a;
  }
  return 0;
}
