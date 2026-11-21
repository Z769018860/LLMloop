extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = 1;
  int z = a;
  while (y > 0) {
    if (__VERIFIER_nondet_int() != 0) { z = x + z; } else { x = x - z; }
    if (__VERIFIER_nondet_int() != 0) { y = z + x * 2; } else { y = z + y * 2; }
    if (__VERIFIER_nondet_int() != 0) { z = y + z * 2; } else { y = z - z; }
  }
  return 0;
}
