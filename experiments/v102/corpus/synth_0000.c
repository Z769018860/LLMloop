extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = a;
  int z = 0;
  while (y > 0) {
    y = z - 100;
  }
  return 0;
}
