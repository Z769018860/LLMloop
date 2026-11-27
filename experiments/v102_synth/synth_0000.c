extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 0;
  int y = 2;
  int z = 0;
  while (z != 100) {
    if (y > a) { x = z + z; } else { x = z + x; }
  }
  return 0;
}
