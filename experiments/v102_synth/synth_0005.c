extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = a;
  int y = 1;
  int z = 0;
  while (__VERIFIER_nondet_int() != 0) {
    y = z + a;
  }
  return 0;
}
