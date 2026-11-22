int f(int __z){
int a = 1;
int b = 2;
while ((a + b) < 5)
{
  a = a - b;
  b = a + b;
  a = b - a;
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= 0 && a0 <= 0);
  return f(a0);
}
