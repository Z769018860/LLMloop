"""Unbounded rectangular pointwise array sweeps with symbolic object lengths.

A sweep enumerates a row-major rectangular domain exactly once. Distinct cells
are independent, so the nested loops are replaced by one array Lambda. SMT
checks bounds/lifetimes and, optionally, every source arithmetic intermediate
under a selected single signed width. No cross-cell recurrence is inferred.
"""
from __future__ import annotations
import ast
from .smt_spath import SMTGraphError,z3,_solver


class SweepMemory:
    def __init__(self,obj):
        if z3 is None:raise SMTGraphError('z3-solver required')
        allowed={'kind','name','parameters','parameter_bounds','objects','pointers','body','queries','signed_bits','entry_evaluated','frontend'}
        if not isinstance(obj,dict) or set(obj)-allowed or obj.get('kind')!='sweep_memory':raise SMTGraphError('Expected sweep_memory with supported fields')
        self.obj=obj;self.parameters=obj.get('parameters',[])
        if not isinstance(self.parameters,list) or not all(isinstance(p,str) and p.isidentifier() for p in self.parameters) or len(set(self.parameters))!=len(self.parameters) or 'old' in self.parameters:raise SMTGraphError('Unique parameter identifiers required')
        self.env={p:z3.Int('sweep_param_'+p) for p in self.parameters}
        self.bits=obj.get('signed_bits')
        if self.bits is not None and (type(self.bits) is not int or self.bits not in (8,16,32,64)):raise SMTGraphError('signed_bits must be 8/16/32/64')
        self.lo=-(1 << (self.bits-1)) if self.bits else None;self.hi=(1 << (self.bits-1))-1 if self.bits else None
        bounds=obj.get('parameter_bounds',{})
        if not isinstance(bounds,dict) or set(bounds)-set(self.parameters):raise SMTGraphError('Unexpected parameter bounds')
        domain=[]
        for p,term in self.env.items():
            limits=bounds.get(p,[None,None])
            if not isinstance(limits,list) or len(limits)!=2 or any(v is not None and type(v) is not int for v in limits):raise SMTGraphError('Bounds must be [min,max]')
            if self.bits:domain.extend([term>=self.lo,term<=self.hi])
            if limits[0] is not None:domain.append(term>=limits[0])
            if limits[1] is not None:domain.append(term<=limits[1])
        self.pre=z3.And(*domain)
        solver=_solver();solver.add(self.pre)
        if solver.check()!=z3.sat:raise SMTGraphError('Empty or undecidable input domain')
        self.objects={};self.pointers={};self.obligations=[];self.failure=None;self.region_certificates=[];self.executed=False;self.proved_queries=set()
        evaluated=obj.get('entry_evaluated',[])
        if not isinstance(evaluated,list) or len(evaluated)>64:raise SMTGraphError('Invalid entry evaluations')
        entry_checks=[]
        for expr in evaluated:self.arith(expr,self.env,entry_checks)
        self.prove('source entry arithmetic',z3.BoolVal(True),z3.And(*entry_checks))
        objects=obj.get('objects',{})
        if not isinstance(objects,dict) or not 1<=len(objects)<=16:raise SMTGraphError('Expected 1..16 logical objects')
        for name,spec in objects.items():
            if not isinstance(name,str) or not name.isidentifier() or not isinstance(spec,dict) or set(spec)-{'length','init','storage'}:raise SMTGraphError('Invalid logical object')
            length=self.arith(spec['length'],self.env,[])
            storage=spec.get('storage','stack')
            if storage not in ('stack','heap'):raise SMTGraphError('storage must be stack or heap')
            self.prove('nonnegative length '+name,z3.BoolVal(True),length>=0,violation_status='UNSUPPORTED_MEMORY_LAYOUT_DOMAIN')
            init=spec.get('init','symbolic')
            if init=='symbolic':memory=z3.Array('sweep_initial_'+name,z3.IntSort(),z3.IntSort())
            else:
                checks=[];value=self.arith(init,self.env,checks)
                memory=z3.K(z3.IntSort(),value)
                self.prove('initial value '+name,z3.BoolVal(True),z3.And(*checks,self.in_range(value)))
            self.objects[name]={'length':length,'memory':memory,'alive':True,'storage':storage}
            # A declared array of C int values starts with values in range.
            if self.bits and init=='symbolic':
                k=z3.Int('sweep_initial_index_'+name)
                self.pre=z3.And(self.pre,z3.ForAll([k],z3.Implies(z3.And(k>=0,k<length),self.in_range(z3.Select(memory,k)))))
        pointers=obj.get('pointers',{})
        if not isinstance(pointers,dict):raise SMTGraphError('pointers must be an object')
        for name,address in pointers.items():self.bind(name,address)

    def in_range(self,value):
        return z3.And(value>=self.lo,value<=self.hi) if self.bits else z3.BoolVal(True)

    def arith(self,text,env,checks):
        if type(text) is int:text=str(text)
        if not isinstance(text,str) or len(text)>2000:raise SMTGraphError('Expected short arithmetic expression')
        tree=ast.parse(text,mode='eval').body
        def rec(n):
            if isinstance(n,ast.Constant) and type(n.value) is int:
                value=z3.IntVal(n.value)
            elif isinstance(n,ast.Name) and n.id in env:return env[n.id]
            elif isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                if isinstance(n.op,ast.USub) and isinstance(n.operand,ast.Constant) and type(n.operand.value) is int:value=z3.IntVal(-n.operand.value)
                else:
                    a=rec(n.operand);value=a if isinstance(n.op,ast.UAdd) else -a
            elif isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult)):
                a,b=rec(n.left),rec(n.right)
                value=a+b if isinstance(n.op,ast.Add) else a-b if isinstance(n.op,ast.Sub) else a*b
            else:raise SMTGraphError('Sweep expressions support integer identifiers and +,-,* only')
            if self.bits:checks.append(self.in_range(value))
            return value
        return rec(tree)

    def prove(self,label,context,claim,indices=None,violation_status='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'):
        if self.failure is not None:return False
        solver=_solver();solver.add(self.pre,context,z3.Not(claim));status=solver.check()
        self.obligations.append({'label':label,'result':str(status)})
        if status==z3.unsat:return True
        if status==z3.unknown:
            self.failure={'status':'UNKNOWN','reason':solver.reason_unknown(),'obligation':label}
        else:
            model=solver.model()
            values=lambda env:{name:model.eval(value,model_completion=True).as_long() for name,value in env.items()}
            self.failure={'status':violation_status,'obligation':label,
                          'witness':{'inputs':values(self.env),'indices':values(indices or {})}}
        return False

    def bind(self,name,address):
        if not isinstance(name,str) or not name.isidentifier() or not isinstance(address,dict):raise SMTGraphError('Invalid pointer binding')
        checks=[]
        if set(address)=={'object','offset'}:
            obj=address['object'];off=self.arith(address['offset'],self.env,checks)
        elif set(address)=={'pointer','offset'}:
            base,offset=self.pointers[address['pointer']];obj=base;off=offset+self.arith(address['offset'],self.env,checks)
        else:raise SMTGraphError('Pointer needs object/offset or pointer/offset')
        if obj not in self.objects:raise SMTGraphError('Unknown pointer object')
        state=self.objects[obj]
        self.prove('pointer formation '+name,z3.BoolVal(True),z3.And(z3.BoolVal(state['alive']),off>=0,off<=state['length'],*checks))
        self.pointers[name]=(obj,off)

    def sweep(self,spec):
        if not isinstance(spec,dict) or set(spec)-{'pointer','offset','dimensions','updates','evaluated_indices'}:raise SMTGraphError('Invalid sweep')
        obj,base=self.pointers[spec['pointer']];state=self.objects[obj]
        offset_checks=[]
        offset=self.arith(spec.get('offset',0),self.env,offset_checks);start=base+offset
        dims=spec.get('dimensions',[])
        if not isinstance(dims,list) or not 1<=len(dims)<=8:raise SMTGraphError('Expected 1..8 sweep dimensions')
        counts=[];indices={};checks=list(offset_checks)
        for d in dims:
            if not isinstance(d,dict) or set(d)!={'index','count'}:raise SMTGraphError('Dimensions require index and count')
            name=d['index']
            if not isinstance(name,str) or not name.isidentifier() or name in self.env or name in indices or name=='old':raise SMTGraphError('Fresh sweep index required')
            count=self.arith(d['count'],self.env,checks)
            counts.append(count);indices[name]=z3.Int('sweep_index_'+name)
        self.prove('sweep count arithmetic',z3.BoolVal(True),z3.And(*checks))
        self.prove('nonnegative sweep counts',z3.BoolVal(True),z3.And(*(c>=0 for c in counts)),violation_status='UNSUPPORTED_SWEEP_COUNT_DOMAIN')
        total=z3.IntVal(1)
        for count in counts:total=total*count
        # The template's row-major bijection maps all tuples to [0,total).
        # Distinct addresses commute because updates may only read their own cell.
        r=z3.Int('sweep_flat_index')
        active=z3.And(r>=0,r<total)
        if not self.prove('sweep lifetime and bounds',active,z3.And(z3.BoolVal(state['alive']),start+r>=0,start+r<state['length']),{'flat':r}):return
        formal=list(indices.values());flat=z3.IntVal(0)
        index_checks=[]
        for index,count in zip(formal,counts):
            if self.bits:index_checks.append(self.in_range(flat*count))
            flat=flat*count+index
            if self.bits:index_checks.append(self.in_range(flat))
        domain=z3.And(*(z3.And(i>=0,i<c) for i,c in zip(formal,counts)))
        evaluated_indices=spec.get('evaluated_indices',[])
        if not isinstance(evaluated_indices,list) or len(evaluated_indices)>128:raise SMTGraphError('Invalid evaluated index list')
        for expr in evaluated_indices:self.arith(expr,{**self.env,**indices},index_checks)
        old=z3.Select(state['memory'],start+flat)
        updates=spec.get('updates')
        if not isinstance(updates,list) or not 1<=len(updates)<=32 or not all(isinstance(x,(str,int)) and not isinstance(x,bool) for x in updates):raise SMTGraphError('updates must be 1..32 sequential own-cell expressions')
        value=old;value_checks=list(index_checks)
        for update in updates:
            value=self.arith(update,{**self.env,**indices,'old':value},value_checks)
        if not self.prove('sweep arithmetic intermediates',domain,z3.And(*value_checks,self.in_range(value)),{**indices,'old':old}):return
        # Decode a flat address by Euclidean quotient/remainder, last index first.
        q=r;coordinates={}
        for name,count in reversed(list(zip(indices,counts))):
            coordinates[indices[name]]=q%count;q=q/count
        selected=z3.substitute(value,*list(coordinates.items()))
        cell=z3.Int('sweep_output_cell')
        relative=cell-start
        new=z3.substitute(selected,(r,relative))
        state['memory']=z3.Lambda([cell],z3.If(z3.And(relative>=0,relative<total),new,z3.Select(state['memory'],cell)))
        self.region_certificates.append({'dimensions':[{'index':d['index'],'count':str(c)} for d,c in zip(dims,counts)],
                                        'domain_size':str(z3.simplify(total)),'object':obj,
                                        'template':'row-major bijection + independent pointwise writes',
                                        'old_cell_only':True})

    def report(self,inputs=None):
        body=self.obj.get('body',[])
        if not isinstance(body,list) or len(body)>64:raise SMTGraphError('body must contain at most 64 operations')
        if not self.executed:
            self.executed=True
            for stage in body:
                if self.failure is not None:break
                if not isinstance(stage,dict) or len(stage)!=1:raise SMTGraphError('Expected one sweep, bind or free operation')
                if 'sweep' in stage:self.sweep(stage['sweep'])
                elif 'bind' in stage:
                    spec=stage['bind']
                    if not isinstance(spec,dict) or set(spec)!={'name','address'}:raise SMTGraphError('Invalid bind')
                    self.bind(spec['name'],spec['address'])
                elif 'free' in stage:
                    obj,offset=self.pointers[stage['free']];state=self.objects[obj]
                    self.prove('free validity',z3.BoolVal(True),z3.And(z3.BoolVal(state['alive'] and state['storage']=='heap'),offset==0))
                    if self.failure is None:state['alive']=False
                else:raise SMTGraphError('Unsupported sweep operation')
        result={'status':'CERTIFIED_UNBOUNDED_POINTWISE_MEMORY','semantics':'signed single-width values with checked intermediates' if self.bits else 'mathematical integers',
                'signed_bits':self.bits,'obligations':self.obligations,'regions':self.region_certificates,
                'scope':'rectangular row-major own-cell sweeps; symbolic lengths and offsets; successful allocation assumed',
                'input_domain_smt2':self.pre.sexpr()}
        if self.failure is not None:return {**result,**self.failure}
        result['objects']={name:{'alive':s['alive'],'storage':s['storage'],'length_smt2':s['length'].sexpr(),
                                 'memory_smt2':s['memory'].sexpr()} for name,s in self.objects.items()}
        queries=self.obj.get('queries',[])
        if not isinstance(queries,list) or len(queries)>64:raise SMTGraphError('At most 64 memory queries')
        substitutions=[]
        if inputs is not None:
            if not isinstance(inputs,dict) or set(inputs)!=set(self.env) or any(type(v) is not int for v in inputs.values()):raise SMTGraphError('Expected integer inputs for every parameter')
            solver=_solver();solver.add(self.pre,*(self.env[p]==v for p,v in inputs.items()))
            if solver.check()!=z3.sat:raise SMTGraphError('Inputs outside the proved domain')
            substitutions=[(self.env[p],z3.IntVal(v)) for p,v in inputs.items()]
        answers=[]
        for query in queries:
            if not isinstance(query,dict) or set(query)!={'pointer','index'}:raise SMTGraphError('Queries require pointer/index')
            obj,base=self.pointers[query['pointer']];state=self.objects[obj]
            checks=[]
            index=base+self.arith(query['index'],self.env,checks)
            key=(query['pointer'],str(query['index']))
            if key not in self.proved_queries:
                if not self.prove('query dereference',z3.BoolVal(True),z3.And(z3.BoolVal(state['alive']),index>=0,index<state['length'],*checks)):
                    return {**result,**self.failure}
                self.proved_queries.add(key)
            value=z3.simplify(z3.substitute(z3.Select(state['memory'],index),*substitutions))
            answers.append({'pointer':query['pointer'],'index':query['index'],
                            **({'value':value.as_long()} if z3.is_int_value(value) else {'value_smt2':value.sexpr()})})
        result['queries']=answers
        return result
