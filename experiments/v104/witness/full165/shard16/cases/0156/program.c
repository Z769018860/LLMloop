int f(int i__in, int j__in, int k__in, int tmp__in){
int tmp = tmp__in;
int k = k__in;
int j = j__in;
int i = i__in;
int c = 0;
while (((i <= 100) && (j <= k)) && (k > (-2147483648)))
{
  tmp = i;
  i = j;
  j = tmp + 1;
  k = k - 1;
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
  int a3 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a3 >= -2147483648 && a3 <= 2147483647);
  return f(a0, a1, a2, a3);
}
