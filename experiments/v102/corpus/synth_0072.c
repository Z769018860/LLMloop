extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 0;
  int y = 1;
  int z = 1;
  while (z != 0) {
    if (x > 0) { x = y + z; } else { y = z - a; }
  }
  return 0;
}
