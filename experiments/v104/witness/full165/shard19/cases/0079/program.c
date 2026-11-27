int f(int i){
int x = 0;
int y = 0;
if (i > 10)
{
  x = 1;
}
else
{
  y = 1;
}

while (x == y)
{
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= -2147483648 && a0 <= 2147483647);
  return f(a0);
}
