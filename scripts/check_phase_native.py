"""Native C/UBSan oracle for state-guarded unbounded periodic summaries."""
from pathlib import Path
import subprocess
import tempfile
import sympy as s
from llmloop.periodic_c import analyze_periodic_c


def main():
    source = (Path(__file__).resolve().parents[1] / 'examples/state_guarded_periodic.c').read_text()
    report = analyze_periodic_c(source, invariants=['sign > 0', 'sign < 0'])
    n, a = s.symbols('n a', integer=True)
    formula = s.sympify(report['return_expr'], locals={'n': n, 'a': a})
    runner = r'''
#include <stdio.h>
int main(void) {
    for (int a=-10;a<=10;a++) {
        for(int n=-3;n<=80;n++) {
            printf("%d %d %d\n", n, a, alternating(n,a));
        }
        printf("%d %d %d\n", 1000000, a, alternating(1000000,a));
    }
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        path, binary = Path(tmp)/'state.c', Path(tmp)/'state'
        path.write_text(source+runner)
        subprocess.run(['cc','-std=c11','-O1','-fsanitize=undefined',
                        '-fno-sanitize-recover=undefined',str(path),'-o',str(binary)],check=True)
        output = subprocess.run([str(binary)],capture_output=True,text=True,check=True).stdout
    count = 0
    for line in output.splitlines():
        iterations, seed, result = map(int,line.split())
        predicted = int(formula.subs({n:iterations,a:seed}))
        if predicted != result:
            raise AssertionError((iterations,seed,predicted,result))
        count += 1
    print(f'State-guarded periodic C/UBSan oracle: {count}/{count}')


if __name__ == '__main__':
    main()
