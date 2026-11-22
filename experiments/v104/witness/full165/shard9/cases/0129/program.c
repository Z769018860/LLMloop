int f(int x, int y__in, int z__in){
int z = z__in;
int y = y__in;
int c = 0;
while ((x > y) && (x > z))
{
  y = y + 1;
  z = z + 1;
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
