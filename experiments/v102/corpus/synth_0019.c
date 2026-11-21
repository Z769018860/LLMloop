extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 1;
  int y = a;
  int z = a;
  while (x > 0) {
    z = y + x;
    z = z + z * 3;
  }
  return 0;
}
