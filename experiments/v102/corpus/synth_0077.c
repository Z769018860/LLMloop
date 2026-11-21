extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = 0;
  int z = 2;
  while (z != 100) {
    x = y + z * 2;
  }
  return 0;
}
