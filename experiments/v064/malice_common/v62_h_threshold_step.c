#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 20000000
    Ensure __return == __return */
{
  int i;
  long x=0;
  /*@ Inv 0 <= x && x <= 2 * i && 0 <= i && i <= n@pre */
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
