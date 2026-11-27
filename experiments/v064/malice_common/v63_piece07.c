#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure __return == __return */
{
  int i;
  long x=0;
  /*@ Inv 0 <= x && x <= 9 * i && 0 <= i && i <= n@pre */
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
