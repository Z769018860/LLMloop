#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 40000
    Ensure __return == __return */
{
  int i;
  long s=0;
  /*@ Inv 0 <= s && s <= 1600000000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    s+=i*i;
  }
  return s;
}
