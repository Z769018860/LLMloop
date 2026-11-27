int f(int __z){
int i = 0;
int x = 0;
int y = 0;
x = __VERIFIER_nondet_int();
y = __VERIFIER_nondet_int();
if (x != 0)
{
  while ((x > 0) && (y > 0))
  {
    i = i + 1;
    x = (x - 1) - (y - 1);
  }

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
