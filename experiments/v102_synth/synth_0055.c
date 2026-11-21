extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 250 || b < 0 || b > 250) return 0;
  int x = 2;
  int y = 0;
  int z = b;
  while (y < 1000) {
    z = x * 4;
    x = y - y;
  }
  return 0;
}
