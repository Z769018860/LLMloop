extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 0;
  int y = b;
  int z = b;
  while (z < 5000 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = x * 4; } else { y = y + y; }
  }
  return 0;
}
