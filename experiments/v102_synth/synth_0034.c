extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 250) return 0;
  int x = 0;
  int y = a;
  int z = 2;
  while (y != 100) {
    if (x < 0) { y = y * 7; } else { y = y - z; }
    z = y - z;
  }
  return 0;
}
