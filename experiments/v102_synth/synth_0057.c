extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = b;
  int y = 1;
  int z = 1;
  while (x > 0) {
    x = b - a;
    y = z * 3;
  }
  return 0;
}
