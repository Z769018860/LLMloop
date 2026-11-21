extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = 2;
  int z = 1;
  while (x != 100) {
    z = x + a;
    z = x + y * 2;
  }
  return 0;
}
