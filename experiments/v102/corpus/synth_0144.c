extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = a;
  int z = 0;
  while (x != 100) {
    x = y + x * 2;
    x = x + z * 2;
  }
  return 0;
}
