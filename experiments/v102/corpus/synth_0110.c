extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 0;
  int y = 1;
  int z = 0;
  while (y != 0) {
    if (x != 0) { x = x * 3; } else { z = a + 7; }
  }
  return 0;
}
