extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = 2;
  int y = 2;
  int z = a;
  while (x < a) {
    z = x * 2;
    y = x * 7;
    y = x + y;
  }
  return 0;
}
