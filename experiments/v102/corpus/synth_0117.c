extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 2;
  int y = a;
  int z = a;
  while (x > 0) {
    z = y - a;
    y = x + y * 2;
  }
  return 0;
}
