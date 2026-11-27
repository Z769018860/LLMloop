int f(int x, int y){
int z = 0;
int i = 0;
i = x;
if ((y > 0) && (x > 0))
{
  while (i > 0)
  {
    i = i - 1;
    z = z + 1;
  }

  while (i < y)
  {
    i = i + 1;
    z = z - 1;
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
