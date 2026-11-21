extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = a;
  int z = 2;
  while (z < 1000) {
    y = z + y * 2;
  }
  return 0;
}
