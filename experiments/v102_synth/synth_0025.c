extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 120 || b < 0 || b > 120) return 0;
  int x = a;
  int y = 2;
  int z = b;
  while (x < a) {
    y = x - z;
  }
  return 0;
}
