extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = 0;
  int z = 1;
  while (x != 0) {
    if (z < 1) { y = x + y; } else { y = z + x * 3; }
  }
  return 0;
}
