extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = 0;
  int y = 2;
  int z = 0;
  while (x < 100) {
    z = y * 4;
    x = y + z;
    z = x * a;
  }
  return 0;
}
