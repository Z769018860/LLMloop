extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 120) return 0;
  int x = 2;
  int y = a;
  int z = 1;
  while (y != 100) {
    if (y != 0) { x = y + y; } else { y = y + x; }
  }
  return 0;
}
