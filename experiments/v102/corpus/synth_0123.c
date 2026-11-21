extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = 0;
  int z = 1;
  while (x > 0) {
    x = z + x * 3;
  }
  return 0;
}
