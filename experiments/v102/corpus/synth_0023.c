extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 2;
  int y = a;
  int z = a;
  while (x < a) {
    z = y - z;
    z = x + z;
    x = z * 7;
  }
  return 0;
}
