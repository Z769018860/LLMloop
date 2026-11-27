#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 30000
    Ensure __return == __return */
{
  int i;
  int a=0;
  long b=0;
  /*@ Inv 0 <= a && a <= 2 * i && 0 <= b && b <= 60000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    a+=2;
    b+=a;
  }
  return b+a;
}
