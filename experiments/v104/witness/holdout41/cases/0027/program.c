int f(int z__in){
int z = z__in;
int x = 0;
int y = 0;
while (z > 0)
{
  x = x + 1;
  y = y - 1;
  z = z - 1;
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
