extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = 2;
  while (x < a) {
    y = x + y * 2;
    x = y * a;
    y = y * 4;
  }
  return 0;
}
