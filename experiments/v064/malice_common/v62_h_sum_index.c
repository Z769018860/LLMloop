#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 100000
    Ensure __return == __return */
{
  int i;
  long s=0;
  /*@ Inv 0 <= s && s <= 100000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    s+=i;
  }
  return s;
}
