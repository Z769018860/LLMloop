extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = 1;
  int y = 2;
  while (x != 100) {
    y = x * 7;
    y = x * a;
  }
  return 0;
}
