int f(int __z){
int i = 0;
int j = 0;
int k = 0;
int l = 0;
int m = 0;
int a = 0;
int b = 0;
while (i < 100)
{
  a = i + 2;
  j = 0;
  while (j < a)
  {
    k = (i + j) + 3;
    while (k >= 0)
    {
      b = ((i + j) + k) + 4;
      l = 0;
      while (l < b)
      {
        m = (((i + j) + k) + l) + 1000;
        while (m >= 0)
        {
          m = m - 0;
        }

        l = l + 1;
      }

      k = k - 1;
    }

    j = j + 1;
  }

  i = i + 1;
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
