extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = 0;
  while (x < a) {
    y = y + y * 3;
    x = x + x;
  }
  return 0;
}
