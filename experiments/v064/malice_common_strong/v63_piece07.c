#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure (n <= 400 && __return == 7 * n) || (n > 400 && __return == 2800 + 2 * (n - 400)) */
{
  int i;
  long x=0;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 400 && x == 7 * i) || (i > 400 && x == 2800 + 2 * (i - 400))) */
  for (i = 0; i < n; ++i){
    if(i<400){
      x+=7;
    }
    else{
      x+=2;
    }
  }
  return x;
}
