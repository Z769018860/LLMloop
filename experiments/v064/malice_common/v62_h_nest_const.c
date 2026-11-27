#include "verification_stdlib.h"

long f(int n,int m)
/*@ Require 0 <= n && n <= 4000 && 0 <= m && m <= 4000
    Ensure __return == __return */
{
  int i;
  int j;
  long x=0;
  /*@ Inv 0 <= x && x <= 8000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
  /*@ Inv 0 <= x && x <= 8000 * i + 2 * j && 0 <= j && j <= m@pre && 0 <= i && i < n@pre */
    for (j = 0; j < m; ++j){
      x+=2;
    }
  }
  return x;
}
