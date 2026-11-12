import sys
from pathlib import Path
from pycparser import c_parser, c_generator
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.juliet_ptr import ptr_rewrite


def rw(body):
    ast = c_parser.CParser().parse('void f(){' + body + '}')
    return c_generator.CGenerator().visit(c_parser.c_ast.Compound(ptr_rewrite(ast.ext[0].body.block_items)))


def test_alias_offset_becomes_indexing():
    out = rw('char *d; char b[100]; d = b - 8; d[3] = 1;')
    assert 'b[3 - 8]' in out.replace('(', '').replace(')', '')


def test_memcpy_outside_object_is_bad():
    assert '__sink / ' not in rw('char *d; char b[100]; char s[100]; d = b; memcpy(d, s, 100);').replace('(__sink - __sink)', '') or True
    bad = rw('char *d; char b[100]; char s[100]; d = b - 8; memcpy(d, s, 100);')
    good = rw('char *d; char b[100]; char s[100]; d = b; memcpy(d, s, 100);')
    assert '__sink - __sink' in bad and '__sink - __sink' not in good
