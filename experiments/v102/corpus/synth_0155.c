extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = 1;
  while (y > 0) {
    y = x * a;
  }
  return 0;
}
