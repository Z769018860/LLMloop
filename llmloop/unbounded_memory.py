"""Compositional unbounded counted loops over finite, statically aliased cells.

Nested repetitions are matrix powers, never per-iteration unrolling. Counts
must be nonnegative polynomials in immutable parameters. Every power has a
checked base/successor identity. No dynamic pointer/index or heap lifetime claim.
"""
from __future__ import annotations
import ast
import sympy as s
from .expressions import parse,integer_value
from .graph_nested import _positive_polynomial
from .recurrence import affine_matrix,certified_power
from .smt_spath import SMTGraphError


class UnboundedMemory:
    def __init__(self,obj):
        if not isinstance(obj,dict):raise SMTGraphError('Expected an object')
        if set(obj)-{'kind','name','parameters','parameter_mins','state','arrays','pointers','body','return_expr','frontend'}:raise SMTGraphError('Unsupported counted_memory fields')
        if obj.get('kind')!='counted_memory':raise SMTGraphError('Expected counted_memory')
        self.obj=obj;self.parameters=tuple(obj.get('parameters',[]))
        if not all(isinstance(v,str) and v.isidentifier() for v in self.parameters):raise SMTGraphError('Parameters must be identifiers')
        if len(set(self.parameters))!=len(self.parameters):raise SMTGraphError('Duplicate parameter')
        self.state=dict(obj.get('state',{}));self.cells={};self.aliases={};self.addresses={}
        if not all(isinstance(v,str) and v.isidentifier() for v in self.state):raise SMTGraphError('State names must be identifiers')
        if set(obj.get('arrays',{})) & (set(self.state)|set(self.parameters)):raise SMTGraphError('Array name collision')
        for name,values in obj.get('arrays',{}).items():
            if not isinstance(name,str) or not name.isidentifier() or not isinstance(values,list) or not 1<=len(values)<=32:
                raise SMTGraphError('Arrays need identifier names and 1..32 initialized cells')
            for index,value in enumerate(values):
                cell=f'{name}__cell_{index}'
                if cell in self.state:raise SMTGraphError('Cell name collision')
                self.state[cell]=value;self.cells[(name,index)]=cell
        for alias,address in obj.get('pointers',{}).items():
            if not isinstance(alias,str) or not alias.isidentifier() or not isinstance(address,dict) or set(address)!={'array','index'}:
                raise SMTGraphError('Pointers require a static array/index address')
            key=(address['array'],address['index'])
            if type(address['index']) is not int or key not in self.cells:raise SMTGraphError('Invalid pointer address')
            self.aliases[alias]=self.cells[key];self.addresses[alias]=key
        if set(self.aliases)&(set(self.state)|set(self.parameters)|set(obj.get('arrays',{}))):raise SMTGraphError('Pointer name collision')
        self.variables=tuple(self.state)
        if not self.variables or len(self.variables)>15 or len(set(self.variables+self.parameters))!=len(self.variables+self.parameters):
            raise SMTGraphError('Expected 1..15 unique cells/scalars disjoint from parameters')
        self.names={v:s.Symbol(v,integer=True) for v in self.variables+self.parameters}
        self.minima=obj.get('parameter_mins',{})
        if set(self.minima)!=set(self.parameters) or any(type(x) is not int for x in self.minima.values()):
            raise SMTGraphError('Supply an integer minimum for every parameter')
        self.initial=s.Matrix([parse(self.rewrite(v),self.names) for v in self.state.values()]+[1])
        if self.initial.free_symbols & {self.names[v] for v in self.variables}:raise SMTGraphError('Initial cells may depend only on parameters')
        self.certificates=[];self.nodes=0
        self.transform=self.compile(obj.get('body',[]),0)

    def target(self,text):
        if text in self.state:return text
        if isinstance(text,str) and text.startswith('*') and text[1:] in self.aliases:return self.aliases[text[1:]]
        tree=ast.parse(text,mode='eval').body
        if isinstance(tree,ast.Subscript) and isinstance(tree.value,ast.Name):
            try:index=ast.literal_eval(tree.slice)
            except (ValueError,TypeError):index=None
            if type(index) is int:
                name=tree.value.id
                if name in self.addresses:
                    array,offset=self.addresses[name];key=(array,offset+index)
                else:key=(name,index)
                if key in self.cells:return self.cells[key]
        raise SMTGraphError('Memory access must identify one live static cell or alias')

    def rewrite(self,text):
        if type(text) is int:return text
        if not isinstance(text,str):raise SMTGraphError('Expected arithmetic expression')
        if text.startswith('*') and text[1:] in self.aliases:return self.aliases[text[1:]]
        tree=ast.parse(text,mode='eval')
        owner=self
        class Cells(ast.NodeTransformer):
            def visit_Subscript(self,node):return ast.copy_location(ast.Name(id=owner.target(ast.unparse(node)),ctx=ast.Load()),node)
            def visit_Name(self,node):
                # Pointer identifiers denote the pointed-to cell in expression IR.
                if node.id in owner.aliases:return ast.copy_location(ast.Name(id=owner.aliases[node.id],ctx=ast.Load()),node)
                return node
        return ast.unparse(Cells().visit(tree))

    def compile(self,body,depth):
        if not isinstance(body,list) or depth>16:raise SMTGraphError('Expected a statement list with nesting depth <=16')
        result=s.eye(len(self.variables)+1)
        for node in body:
            self.nodes+=1
            if self.nodes>128 or not isinstance(node,dict):raise SMTGraphError('Statement budget exceeded or malformed statement')
            if set(node)=={'assign'}:
                assignments=node['assign']
                if not isinstance(assignments,dict) or not assignments:raise SMTGraphError('assign needs simultaneous cell updates')
                updates={}
                for target,value in assignments.items():
                    cell=self.target(target)
                    if cell in updates:raise SMTGraphError('Simultaneous assignments alias the same cell')
                    updates[cell]=self.rewrite(value)
                step=affine_matrix(self.variables,self.names,updates)
            elif set(node)=={'repeat','body'}:
                count=parse(node['repeat'],self.names)
                if count.free_symbols-{self.names[v] for v in self.parameters} or not _positive_polynomial(count,self.minima):
                    raise SMTGraphError('Repeat count must be a proven nonnegative polynomial in immutable parameters')
                inner=self.compile(node['body'],depth+1)
                step,certificate=certified_power(inner,count)
                self.certificates.append({'depth':depth,'count':str(count),**certificate})
            else:raise SMTGraphError('Expected assign or counted repeat/body statement')
            result=(step*result).applyfunc(s.simplify)
        return result

    def report(self,inputs=None):
        final=(self.transform*self.initial).applyfunc(s.simplify)
        report={'status':'CERTIFIED_UNBOUNDED_COUNTED_MEMORY','semantics':'mathematical integers',
                'final_state':{v:str(final[i]) for i,v in enumerate(self.variables)},
                'parameter_mins':self.minima,'power_certificates':self.certificates,
                'aliases':self.aliases,'cell_model':{f'{a}[{i}]':v for (a,i),v in self.cells.items()},
                'scope':'finite initialized objects; static aliases and indices; immutable counted loops; no per-iteration unrolling',
                'c_overflow_verified':False}
        if 'return_expr' in self.obj:
            expression=parse(self.rewrite(self.obj['return_expr']),self.names)
            returned=s.simplify(expression.subs({self.names[v]:final[i] for i,v in enumerate(self.variables)},simultaneous=True))
            report['return_expr']=str(returned)
        if inputs is not None:
            if set(inputs)!=set(self.parameters) or any(type(x) is not int or x<self.minima[p] for p,x in inputs.items()):raise SMTGraphError('Inputs violate the parameter domain')
            report['evaluation']={v:integer_value(final[i],inputs) for i,v in enumerate(self.variables)}
            if 'return_expr' in self.obj:report['return_value']=integer_value(returned,inputs)
        return report
