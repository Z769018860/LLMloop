"""Compare certified periodic formulas with native C under UBSan."""
import json
from pathlib import Path
import subprocess
import tempfile
import sympy as s
from llmloop.periodic_recurrence import summarize_periodic


def main():
    obj = json.loads((Path(__file__).resolve().parents[1] / 'examples/periodic_recurrence.json').read_text())
    report = summarize_periodic(obj)
    k = s.Symbol('k', integer=True, nonnegative=True)
    a = s.Symbol('a', integer=True)
    formulas = [s.sympify(report['final_state'][v], locals={'k': k, 'a': a}) for v in ['x', 'y']]
    source = r'''
#include <stdio.h>
int main(void) {
    for (long long a=-10; a<=10; a++) {
        long long x=a, y=1;
        for (int k=0; k<=50; k++) {
            printf("%lld %d %lld %lld\n", a, k, x, y);
            if (k%2==0) { x=x+y; y=y+1; }
            else { x=2*x-y; }
        }
    }
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        cfile, binary = Path(tmp)/'periodic.c', Path(tmp)/'periodic'
        cfile.write_text(source)
        subprocess.run(['cc', '-std=c11', '-O1', '-fsanitize=undefined',
                        '-fno-sanitize-recover=undefined', str(cfile), '-o', str(binary)], check=True)
        output = subprocess.run([str(binary)], text=True, capture_output=True, check=True).stdout
    count = 0
    for line in output.splitlines():
        seed, n, x, y = map(int, line.split())
        predicted = [int(f.subs({a: seed, k: n})) for f in formulas]
        if predicted != [x, y]:
            raise AssertionError((seed, n, predicted, [x, y]))
        count += 1
    print(f'Periodic affine C/UBSan oracle: {count}/{count}')


if __name__ == '__main__':
    main()
