extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = a;
  while (x < 1000) {
    y = x - y;
    x = x * 2;
  }
  return 0;
}
