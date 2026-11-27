#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure (n <= 447 && __return == 7 * n) || (n > 447 && __return == 3129 + 2 * (n - 447)) */
{
  int i;
  long x=0;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 447 && x == 7 * i) || (i > 447 && x == 3129 + 2 * (i - 447))) */
  for (i = 0; i < n; ++i){
    if(i<447){
      x+=7;
    }
    else{
      x+=2;
    }
  }
  return x;
}
