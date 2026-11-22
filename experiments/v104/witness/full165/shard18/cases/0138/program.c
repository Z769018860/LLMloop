int f(int x__in, int tmp__in){
int tmp = tmp__in;
int x = x__in;
while ((((x > 0) && (tmp < 1073741824)) && ((-1073741824) < tmp)) && (x == (2 * tmp)))
{
  x = x - 1;
  tmp = __VERIFIER_nondet_int();
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
  return f(a0, a1);
}
