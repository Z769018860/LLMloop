#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 20000000
    Ensure (n <= 100 && __return == 2 * n) || (n > 100 && __return == 200 + (n - 100)) */
{
  int i;
  long x=0;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 100 && x == 2 * i) || (i > 100 && x == 200 + (i - 100))) */
  for (i = 0; i < n; ++i){
    if(i<100){
      x+=2;
    }
    else{
      x+=1;
    }
  }
  return x;
}
