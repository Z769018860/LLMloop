"""Exact, budgeted integer choices from syntax; never infer a numeric bound.

Every returned guard/value partition is exhaustive by structural construction.
Unknown inputs, excessive combinations and nonnumeral results refuse rewriting.
Conditions are opaque, so no assumption about their truth is introduced.
"""
from itertools import product

import z3


def integer_choices(expression, max_cases=8, max_nodes=128, max_combinations=128):
    cache={};visited=0;combinations=0
    operators={z3.Z3_OP_ADD,z3.Z3_OP_SUB,z3.Z3_OP_MUL,z3.Z3_OP_UMINUS,z3.Z3_OP_MOD,z3.Z3_OP_IDIV}
    def merge(pairs):
        values={}
        for value,guard in pairs:
            values[value]=z3.Or(values[value],guard) if value in values else guard
        if len(values)>max_cases:return None
        return {value:z3.simplify(guard) for value,guard in values.items()}
    def visit(node,depth=0):
        nonlocal visited,combinations
        key=node.get_id()
        if key in cache:return cache[key]
        visited+=1
        if visited>max_nodes or depth>32 or not z3.is_int(node):return None
        if z3.is_int_value(node):result={node.as_long():z3.BoolVal(True)}
        elif z3.is_app_of(node,z3.Z3_OP_ITE):
            yes,no=visit(node.arg(1),depth+1),visit(node.arg(2),depth+1)
            if yes is None or no is None:result=None
            else:
                condition=node.arg(0)
                result=merge([(v,z3.And(condition,g)) for v,g in yes.items()]+
                             [(v,z3.And(z3.Not(condition),g)) for v,g in no.items()])
        elif z3.is_app(node) and node.decl().kind() in operators:
            children=[visit(child,depth+1) for child in node.children()]
            if any(child is None for child in children):result=None
            else:
                count=1
                for child in children:count*=len(child)
                combinations+=count
                if combinations>max_combinations:return None
                pairs=[]
                for combination in product(*(child.items() for child in children)):
                    value=z3.simplify(node.decl()(*(z3.IntVal(v) for v,_ in combination)))
                    # Integer division/modulo by zero remains an uninterpreted
                    # value in SMT; it must never become a guessed constant.
                    if not z3.is_int_value(value):return None
                    pairs.append((value.as_long(),z3.And(*(g for _,g in combination))))
                result=merge(pairs)
        else:result=None
        cache[key]=result
        return result
    return visit(expression)


def choice_value(choices):
    """Rebuild only a complete partition produced by integer_choices."""
    value=z3.IntVal(0)
    for number,guard in choices.items():value=z3.If(guard,z3.IntVal(number),value)
    return z3.simplify(value)
