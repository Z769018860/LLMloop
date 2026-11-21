extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = 2;
  int z = 2;
  while (y > 0) {
    if (z == 0) { y = y - z; } else { x = z - x; }
    y = z + z * 3;
  }
  return 0;
}
