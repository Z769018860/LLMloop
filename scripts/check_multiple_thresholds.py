"""Differential check: certified models versus native C at two optimization levels."""
import ctypes
from pathlib import Path
import subprocess
import tempfile

from llmloop.typed_nested import TypedCNested

SOURCES = [
    'long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x++;}if(i<3){x++;}}return x;}',
    'long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<=t){x+=2;}else{x+=1;}if(i>3){x+=3;}if(i>=5){x+=4;}}return x;}',
]


def main():
    comparisons = 0
    with tempfile.TemporaryDirectory(prefix='llmloop-phases-') as directory:
        root = Path(directory)
        for number, source in enumerate(SOURCES):
            engine = TypedCNested(source, 'auto', parameter_bounds={'n': [0, 20], 't': [-5, 20]})
            result = engine.report()
            if result['status'] != 'PROVED_DEFINED_TYPED_C_NESTED':
                raise RuntimeError(str(result))
            c_file = root / f'case{number}.c'
            c_file.write_text(source)
            for level in ('-O0', '-O2'):
                library = root / f'case{number}{level}.so'
                subprocess.run(['gcc', level, '-shared', '-fPIC', str(c_file), '-o', str(library)], check=True)
                function = ctypes.CDLL(str(library)).f
                function.argtypes = [ctypes.c_int, ctypes.c_int]
                function.restype = ctypes.c_long
                for n in range(21):
                    for t in range(-5, 21):
                        expected = engine.report({'n': n, 't': t})['evaluation']['value']
                        actual = function(n, t)
                        if expected != actual:
                            raise AssertionError((number, level, n, t, expected, actual))
                        comparisons += 1
    print(f'{comparisons} native/model comparisons passed')


if __name__ == '__main__':
    main()
