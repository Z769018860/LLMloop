extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = a;
  int z = 0;
  while (z > 0) {
    x = x * a;
    z = y * 4;
    z = z + x * 3;
  }
  return 0;
}
