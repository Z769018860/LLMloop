"""Check physical parameter spellings before C's array adjustment erases syntax."""
import re

from .smt_spath import SMTGraphError


def checked_pointer_parameter(parameter, raw, resolved, canonical_type,allow_static=False):
    """Admit a literal pointer or one unqualified outer array.

    Only [] or a positive unsuffixed decimal literal is admitted. Ordinary
    array bounds impose no minimum object extent (C11 6.7.6.3p7). Actual
    pointer accesses still belong to the receiving finite-memory obligations.
    Static minima 1..8 are optional checked entry contracts, never assumptions.
    """
    name=parameter.get('name')
    suffix=r'(?:\[\s*(?:(static)\s+)?([1-9][0-9]*|)\s*\])?'
    prefix=r'([A-Za-z_][A-Za-z0-9_\s*]*?)'
    if name:
        pattern=prefix+r'\s*\b'+re.escape(name)+r'\s*'+suffix+r'\s*'
    else:
        pattern=prefix+r'\s*'+suffix+r'\s*'
    match=re.fullmatch(pattern,' '.join(raw.split()))
    if match:
        element=match[1].strip();static=match[2] is not None;bound=match[3]
        if static and (not allow_static or bound not in tuple('12345678')):
            raise SMTGraphError('Clang pointer parameters require literal pointer or ordinary array declarators; static array contracts require calls backend and literal minimum 1..8')
        adjusted=canonical_type(element+(' *' if bound is not None else ''))
        if adjusted==resolved:
            if bound is None:return None
            return {'parameter_id':parameter['id'],'parameter_name':name,'source_spelling':raw,
                    'outer_array_bound':bound or None,'adjusted_type':adjusted,
                    'minimum_extent_assumed':False,'bound_evaluation_required':False,
                    'rule':'C11 6.7.6.3p7 array parameter adjustment',
                    **({'minimum_extent_required':int(bound)} if static else {})}
    raise SMTGraphError('Clang pointer parameters require literal pointer or ordinary array declarators; static/VLA/qualified/multidimensional and unavailable macro/header spellings unsupported')
