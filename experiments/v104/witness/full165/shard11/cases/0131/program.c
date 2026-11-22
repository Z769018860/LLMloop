int f(int x, int y, int z__in){
int z = z__in;
while (((y > 0) && (x >= z)) && (z <= (2147483647 - y)))
{
  z = z + y;
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= -2147483648 && a0 <= 2147483647);
  int a1 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a1 >= -2147483648 && a1 <= 2147483647);
  int a2 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a2 >= -2147483648 && a2 <= 2147483647);
  return f(a0, a1, a2);
}
