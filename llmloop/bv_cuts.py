"""Checked packed-byte cut certificates for independent popcount equivalence.

Mask shape only proposes a cut. Every byte identity/bound must be proved; no
algorithm fact is assumed. The final small word equation is translated exactly
to bounded integer arithmetic, then proved after certified affine normalization.
"""
import time

import z3

from .bounded_affine import normalize_bounded_affine
from .smt_spath import SMTGraphError


def qfbv_terms(roots,max_nodes=32768):
    pending=list(roots);seen=set();variables={}
    while pending:
        term=pending.pop();key=term.get_id()
        if key in seen:continue
        seen.add(key)
        if len(seen)>max_nodes:raise SMTGraphError('QF_BV expression budget exceeded')
        if z3.is_quantifier(term) or term.sort().kind() not in (z3.Z3_BOOL_SORT,z3.Z3_BV_SORT):raise SMTGraphError('Functional reference query is not QF_BV')
        if term.decl().kind()==z3.Z3_OP_UNINTERPRETED:
            if term.num_args():raise SMTGraphError('Uninterpreted function in QF_BV reference')
            variables[key]=term
        pending.extend(term.children())
    return variables


def word_to_integer(root,bindings,max_nodes=4096):
    """Unsigned mathematical value of an admitted fixed-shift BV word DAG.

    bindings map BV variables to bounded integer variables. The caller must
    prove 0 <= binding < 2**width; this translator introduces no assumptions.
    """
    mapping={b.get_id():i for b,i in bindings};cache={}
    if len(mapping)!=len(bindings) or any(not z3.is_bv(b) or not z3.is_const(b) or b.decl().kind()!=z3.Z3_OP_UNINTERPRETED or not z3.is_int(i) or not z3.is_const(i) or i.decl().kind()!=z3.Z3_OP_UNINTERPRETED for b,i in bindings):raise SMTGraphError('Invalid BV/integer bindings')
    def visit(term,depth=0):
        key=term.get_id()
        if key in cache:return cache[key]
        if len(cache)>=max_nodes or depth>128:raise SMTGraphError('BV/integer translation budget exceeded')
        if key in mapping:result=mapping[key]
        elif z3.is_bv_value(term):result=z3.IntVal(term.as_long())
        elif not z3.is_bv(term) or not z3.is_app(term) or term.size()>128:raise SMTGraphError('Unsupported word expression')
        else:
            kind=term.decl().kind();children=term.children();values=[visit(child,depth+1) for child in children];modulus=1<<term.size()
            if kind==z3.Z3_OP_CONCAT:
                result=values[0]
                for child,value in zip(children[1:],values[1:]):result=result*(1<<child.size())+value
            elif kind==z3.Z3_OP_EXTRACT:
                high,low=term.params();result=(values[0]/(1<<low))%modulus
            elif kind==z3.Z3_OP_ZERO_EXT:result=values[0]
            elif kind==z3.Z3_OP_BADD:result=z3.Sum(*values)%modulus
            elif kind==z3.Z3_OP_BSUB:result=(values[0]-values[1])%modulus
            elif kind==z3.Z3_OP_BNEG:result=(-values[0])%modulus
            elif kind==z3.Z3_OP_BMUL and any(z3.is_bv_value(c) for c in children):result=(values[0]*values[1])%modulus
            elif kind in (z3.Z3_OP_BLSHR,z3.Z3_OP_BSHL) and z3.is_bv_value(children[1]):
                shift=children[1].as_long()
                result=z3.IntVal(0) if shift>=children[0].size() else values[0]/(1<<shift) if kind==z3.Z3_OP_BLSHR else values[0]*(1<<shift)%modulus
            elif kind==z3.Z3_OP_BAND and len(children)==2 and any(z3.is_bv_value(c) for c in children):
                index=0 if z3.is_bv_value(children[0]) else 1;mask=children[index].as_long()
                if mask&(mask+1):raise SMTGraphError('Only low-bit word masks admitted in integer translation')
                result=values[1-index]%(mask+1)
            else:raise SMTGraphError('Unsupported BV operator in integer word certificate: '+str(term.decl()))
        cache[key]=z3.simplify(result,som=True);return cache[key]
    return visit(root)


def packed_popcount_proof(output,reference,input_word,timeout_ms=5000):
    """Return a checked certificate or None when structural discovery refuses.

    UNKNOWN/refused lemmas never establish output equivalence. All solver calls
    and preparation share the same total deadline, with no retries.
    """
    if type(timeout_ms) is not int or not 1<=timeout_ms<=5000:raise SMTGraphError('Packed proof budget must be 1..5000 ms')
    start=time.monotonic();deadline=start+timeout_ms/1000
    if not z3.is_bv(input_word) or not z3.is_const(input_word) or input_word.decl().kind()!=z3.Z3_OP_UNINTERPRETED or input_word.size() not in (32,64):return None
    if not z3.is_bv(output) or not z3.is_bv(reference) or output.size()!=reference.size():return None
    qfbv_terms([output,reference])
    steps=[];width=input_word.size();lanes=width//8
    mask=int('0f'*lanes,16);pending=[output];seen=set();candidates=[]
    while pending:
        term=pending.pop()
        if term.get_id() in seen:continue
        seen.add(term.get_id())
        if z3.is_app_of(term,z3.Z3_OP_BAND) and term.size()==width and any(z3.is_bv_value(c) and c.as_long()==mask for c in term.children()):candidates.append(term)
        pending.extend(term.children())
    if len(candidates)!=1:return None
    cut=candidates[0];counts=[];counters=[]
    for lane in range(lanes):
        parts=[z3.Extract(lane*8+i,lane*8+i,input_word) for i in range(8)]
        while len(parts)>1:parts=[z3.ZeroExt(1,parts[i])+z3.ZeroExt(1,parts[i+1]) for i in range(0,len(parts),2)]
        counts.append(parts[0]);counters.append(z3.FreshConst(z3.BitVecSort(4),prefix='packed_byte'))
    packed=z3.Concat(*(z3.ZeroExt(4,c) for c in reversed(counters)))
    reduced_output=z3.simplify(z3.substitute(output,(cut,packed)))
    reduced_reference=z3.simplify(z3.substitute(reference,*zip(counts,counters)))
    allowed={c.get_id() for c in counters}
    if not set(qfbv_terms([reduced_output,reduced_reference]))<=allowed:return None

    def query(name,claims,logic):
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0:return 'unknown'
        solver=z3.SolverFor(logic);solver.set(timeout=remaining);solver.add(*claims)
        began=time.monotonic();answer=solver.check()
        step={'name':name,'logic':logic,'result':str(answer),'timeout_ms':remaining,
              'elapsed_seconds':round(time.monotonic()-began,6),'refutation_smt2':solver.to_smt2()}
        if answer==z3.unknown:step['reason']=solver.reason_unknown()
        steps.append(step);return str(answer)

    result={'status':'UNKNOWN','query_result':'unknown','method':'checked packed-byte BV cuts and exact bounded integer word equation',
            'timeout_ms':timeout_ms,'total_timeout_ms':timeout_ms,'steps':steps,'cut_smt2':cut.sexpr(),
            'composition_rule':'all disjoint byte identities and bounds, exhaustive packing, exact word translation, bounded affine rewrites, final integer equality',
            'source_word_bits':width,'byte_count':lanes,'source_input':input_word.sexpr(),
            'reduced_output_bv':reduced_output.sexpr(),'reduced_reference_bv':reduced_reference.sexpr(),
            'counter_bindings':[{'counter':c.sexpr(),'reference':r.sexpr(),'bounds':[0,8]} for c,r in zip(counters,counts)],
            'refutation_smt2':None,'refutation_scope':'bounded integer root only; all byte and packing steps plus the recorded translations are required',
            'trusted_components':['typed source executor','cut composition rule','exact BV/unsigned-integer translator','bounded affine normalizer','SMT solver']}
    def finish(reason=None):
        result['elapsed_seconds']=round(time.monotonic()-start,6)
        if reason:result['reason']=reason
        return result
    for lane,count in enumerate(counts):
        byte=z3.Extract(lane*8+7,lane*8,cut)
        answer=query('byte_identity_and_bound_'+str(lane),[z3.Or(byte!=z3.ZeroExt(4,count),z3.UGT(count,8))],'QF_BV')
        if answer!='unsat':return finish('byte cut identity/bound not proved: '+str(lane))
    packing=z3.Concat(*(z3.Extract(lane*8+7,lane*8,cut) for lane in reversed(range(lanes))))
    if query('exhaustive_byte_packing',[cut!=packing],'QF_BV')!='unsat':return finish('packing identity unproved')
    integer_counters=[z3.FreshInt('packed_count') for _ in counters]
    bindings=list(zip(counters,integer_counters));bounds=[(variable,0,8) for variable in integer_counters]
    try:
        integer_output=word_to_integer(reduced_output,bindings);integer_reference=word_to_integer(reduced_reference,bindings)
        normal_output,output_certificate=normalize_bounded_affine(integer_output,bounds)
        normal_reference,reference_certificate=normalize_bounded_affine(integer_reference,bounds)
    except SMTGraphError as exc:return finish(str(exc))
    if not output_certificate['complete'] or not reference_certificate['complete']:return finish('affine normalization budget exhausted')
    result.update(integer_bindings=[{'bv':b.sexpr(),'integer':i.sexpr(),'bounds':[0,8]} for b,i in bindings],
                  integer_output=integer_output.sexpr(),integer_reference=integer_reference.sexpr(),
                  normalized_output=normal_output.sexpr(),normalized_reference=normal_reference.sexpr(),
                  output_normalization=output_certificate,reference_normalization=reference_certificate)
    answer=query('bounded_integer_root',[*(z3.And(c>=0,c<=8) for c in integer_counters),normal_output!=normal_reference],'QF_LIA')
    if answer=='unsat':result.update(status='PROVED_FUNCTIONAL_BV_CUTS',query_result='unsat',refutation_smt2=steps[-1]['refutation_smt2'])
    return finish(None if answer=='unsat' else 'final integer equation unproved')
