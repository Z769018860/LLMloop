int f(int n, int m){
int v1 = 0;
int v2 = 0;
if ((n >= 0) && (m > 0))
{
  v1 = n;
  v2 = 0;
  while (v1 > 0)
  {
    if (v2 < m)
    {
      v2 = v2 + 1;
      v1 = v1 - 1;
    }
    else
    {
      v2 = 0;
    }
  }

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
