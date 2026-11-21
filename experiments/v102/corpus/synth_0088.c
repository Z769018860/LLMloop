extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 2;
  int y = 1;
  int z = 1;
  while (y < a) {
    if (__VERIFIER_nondet_int() != 0) { y = x + y * 3; } else { y = z + z * 2; }
    z = y * 4;
  }
  return 0;
}
