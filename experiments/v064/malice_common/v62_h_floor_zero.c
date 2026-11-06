#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 2000000
    Ensure __return == __return */
{
  int i;
  int x=1000000;
  /*@ Inv 0 <= x && x <= 1000000 && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    if(x>0){
      x--;
    }
  }
  return x;
}
