#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 20000
    Ensure __return == __return */
{
  int i;
  long a=0,b=0;
  /*@ Inv 0 <= a && a <= 6 * i && 0 <= b && b <= 120011 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    a+=4;
    b+=a+5;
  }
  return b;
}
