"""Exact affine div/mod normalization under explicit integer bounds.

Bounds are hypotheses supplied by the caller, never inferred C safety facts.
For A=D*Q+R, a proved single quotient interval for R determines div/mod exactly.
"""
import z3

from .smt_spath import SMTGraphError


def normalize_bounded_affine(root, bindings, max_nodes=4096, max_terms=32):
    variables={};bounds={}
    for variable,lo,hi in bindings:
        if not z3.is_const(variable) or not z3.is_int(variable) or variable.decl().kind()!=z3.Z3_OP_UNINTERPRETED:
            raise SMTGraphError('Affine bounds require integer variables')
        if type(lo) is not int or type(hi) is not int or lo>hi or max(abs(lo).bit_length(),abs(hi).bit_length())>1024:
            raise SMTGraphError('Invalid bounded affine interval')
        if variable.get_id() in variables:raise SMTGraphError('Duplicate affine bound variable')
        variables[variable.get_id()]=variable;bounds[variable.get_id()]=(lo,hi)
    if not z3.is_int(root) or type(max_nodes) is not int or type(max_terms) is not int or not 1<=max_nodes<=16384 or not 1<=max_terms<=128:raise SMTGraphError('Invalid affine normalization root/budget')
    cache={};polynomials={};checks=[];visits=0;complete=True

    def affine(node):
        nonlocal visits,complete
        key=node.get_id()
        if key in polynomials:return polynomials[key]
        visits+=1
        if visits>max_nodes:complete=False;return None
        if z3.is_int_value(node):result=({},node.as_long())
        elif key in variables:result=({key:1},0)
        elif not z3.is_app(node):result=None
        else:
            kind=node.decl().kind();parts=[affine(child) for child in node.children()]
            if any(part is None for part in parts):result=None
            elif kind in (z3.Z3_OP_ADD,z3.Z3_OP_SUB,z3.Z3_OP_UMINUS):
                coefficients={};constant=0
                for index,(terms,value) in enumerate(parts):
                    sign=-1 if kind==z3.Z3_OP_UMINUS or kind==z3.Z3_OP_SUB and index>0 else 1
                    constant+=sign*value
                    for atom,coefficient in terms.items():coefficients[atom]=coefficients.get(atom,0)+sign*coefficient
                result=({k:v for k,v in coefficients.items() if v},constant)
            elif kind==z3.Z3_OP_MUL:
                factor=1;nonconstant=[]
                for terms,value in parts:
                    if terms:nonconstant.append((terms,value))
                    else:factor*=value
                if len(nonconstant)>1:result=None
                elif not nonconstant:result=({},factor)
                else:
                    terms,value=nonconstant[0];result=({k:factor*v for k,v in terms.items() if factor*v},factor*value)
            else:result=None
        if result is not None and (len(result[0])>max_terms or any(abs(v).bit_length()>1024 for v in [*result[0].values(),result[1]])):
            complete=False;result=None
        polynomials[key]=result;return result

    def emit(terms,constant):
        return z3.simplify(z3.IntVal(constant)+z3.Sum(*(coefficient*variables[key] for key,coefficient in terms.items())),som=True)

    def visit(node,depth=0):
        nonlocal visits,complete
        key=node.get_id()
        if key in cache:return cache[key]
        visits+=1
        if visits>max_nodes or depth>128:complete=False;return node
        if z3.is_quantifier(node):raise SMTGraphError('Quantified affine expressions unsupported')
        children=[visit(child,depth+1) for child in node.children()]
        result=node.decl()(*children) if children else node
        kind=node.decl().kind()
        if kind in (z3.Z3_OP_IDIV,z3.Z3_OP_MOD) and z3.is_int_value(children[1]) and children[1].as_long()>0:
            argument=z3.simplify(children[0],som=True);polynomial=affine(argument);divisor=children[1].as_long()
            if polynomial is not None:
                terms,constant=polynomial
                residual={k:c%divisor for k,c in terms.items() if c%divisor}
                residue_constant=constant%divisor
                lo=residue_constant+sum(c*bounds[k][0] for k,c in residual.items())
                hi=residue_constant+sum(c*bounds[k][1] for k,c in residual.items())
                if lo//divisor==hi//divisor:
                    quotient=emit({k:c//divisor for k,c in terms.items() if c//divisor},constant//divisor+lo//divisor)
                    remainder=emit(residual,residue_constant-(lo//divisor)*divisor)
                    identity=z3.simplify(argument-divisor*quotient-remainder,som=True)
                    remainder_interval=[lo-(lo//divisor)*divisor,hi-(lo//divisor)*divisor]
                    if not z3.is_int_value(identity) or identity.as_long()!=0 or not 0<=remainder_interval[0]<=remainder_interval[1]<divisor:
                        raise SMTGraphError('Affine quotient/remainder audit failed')
                    result=quotient if kind==z3.Z3_OP_IDIV else remainder
                    checks.append({'argument':argument.sexpr(),'divisor':divisor,'quotient':quotient.sexpr(),
                                   'remainder':remainder.sexpr(),'residual_interval':[lo,hi],
                                   'residual_quotient':lo//divisor,'remainder_interval':remainder_interval,
                                   'decomposition_identity_checked':True,'operation':'div' if kind==z3.Z3_OP_IDIV else 'mod'})
        result=z3.simplify(result,som=True);cache[key]=result;return result

    normalized=visit(root)
    return normalized,{'method':'exact affine coefficient quotient/remainder with bounded residual interval',
                       'bounds':{str(variables[k]):list(v) for k,v in bounds.items()},'rewrites':checks,'complete':complete}
