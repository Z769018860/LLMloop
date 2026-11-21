extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = a;
  while (x != 0) {
    y = x * 3;
    x = x - 100;
  }
  return 0;
}
