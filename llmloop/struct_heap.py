"""Named, naturally aligned finite heap records without physical address casts."""
from dataclasses import dataclass,field
from pycparser import c_ast,c_parser
import z3
from .typed_memory import Object
from .symbolic_integers import TypedTerm
from .smt_spath import SMTGraphError


@dataclass(frozen=True)
class StructType:
    tag: str
    bits: int=field(default=0,compare=False)

    @property
    def name(self):return 'struct '+self.tag


class StructHeap:
    def __init__(self,owner,source):
        self.owner=owner;self.definitions={};self.types={};self.fields={};self.layouts={}
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        for item in unit.ext:
            if not isinstance(item,c_ast.Decl) or item.name is not None or not isinstance(item.type,c_ast.Struct):continue
            record=item.type
            if record.decls is None:continue
            if not record.name or record.name in self.definitions:raise SMTGraphError('Unique named top-level struct definitions required')
            if not 1<=len(record.decls)<=8:raise SMTGraphError('Structs require 1..8 scalar/pointer fields')
            self.definitions[record.name]=record
        if len(self.definitions)>8:raise SMTGraphError('Struct type budget is 8')
        self.types={name:StructType(name) for name in self.definitions}

    def prepare(self):
        o=self.owner;pointer_size=4 if o.engine.abi.model=='ILP32' else 8
        for name,definition in self.definitions.items():
            fields={};offset=0;alignment=1;layout=[]
            for member in definition.decls:
                if not member.name or member.name in fields or member.bitsize is not None or member.init is not None or member.storage or member.quals:raise SMTGraphError('Unique unqualified non-bitfield struct members required')
                if not isinstance(member.type,(c_ast.TypeDecl,c_ast.PtrDecl)):raise SMTGraphError('Struct members must be integers or typed pointers')
                t=o.memory_type(member.type)
                if isinstance(t,StructType):raise SMTGraphError('Embedded/by-value structs unsupported')
                size=max(1,t.bits//8);align=min(size,pointer_size)
                offset=(offset+align-1)//align*align
                fields[member.name]=t;layout.append({'field':member.name,'offset':offset,'size':size,'alignment':align})
                offset+=size;alignment=max(alignment,align)
            size=(offset+alignment-1)//alignment*alignment
            self.types[name]=StructType(name,size*8);self.fields[name]=fields
            self.layouts[name]={'size':size,'alignment':alignment,'members':layout}

    def type(self,node):
        if not isinstance(node,c_ast.TypeDecl) or not isinstance(node.type,c_ast.Struct):return None
        record=node.type
        if record.decls is not None or record.name not in self.types:raise SMTGraphError('Use an available named top-level struct type')
        return self.types[record.name]

    def field_type(self,node):
        if node.type!='->' or not isinstance(node.field,c_ast.ID):raise SMTGraphError('Struct access requires pointer -> named field')
        t=self.owner.pointee_type(node.name)
        if not isinstance(t,StructType) or t.tag not in self.fields:raise SMTGraphError('Member access requires a typed record pointer')
        if node.field.name not in self.fields[t.tag]:raise SMTGraphError('Unknown struct field')
        return self.fields[t.tag][node.field.name]

    def make_object(self,node,t,length,heap,zeroed,env,guard):
        o=self.owner
        if not heap:raise SMTGraphError('Only allocated single-record structs supported')
        o.check('struct allocation contains exactly one record',z3.And(o.domain,guard),length==1)
        members=self.fields[t.tag]
        if len(o.objects)>=8 or sum(len(obj.cells) for obj in o.objects.values())+len(members)>64:raise SMTGraphError('Dynamic struct heap instance/cell budget exceeded')
        boolean=o.engine.abi.types['_Bool'];tag=node.name+'@'+str(len(o.objects))
        cells=[o.field(tag+'.'+name,kind) for name,kind in members.items()]
        initialized=[o.field('initialized:'+tag+'.'+name,boolean,True) for name in members]
        obj=Object(tag,t,z3.IntVal(1),True,zeroed,cells,initialized,o.field('alive:'+tag,boolean,True))
        obj.scope=None;obj.site=id(node);obj.members=dict(zip(members,zip(cells,initialized)))
        o.objects[len(o.objects)]=obj
        return obj

    def initialize(self,obj,env):
        from .typed_cfg_heap import PointerElement,Pointer
        o=self.owner;new=dict(env);boolean=o.engine.abi.types['_Bool'];new[obj.alive]=TypedTerm(z3.IntVal(1),boolean,z3.BoolVal(True))
        for name,t in self.fields[obj.type.tag].items():
            cell,flag=obj.members[name]
            if isinstance(t,PointerElement):
                new[cell]=Pointer(None,TypedTerm(z3.IntVal(0),o.engine.abi.types['long long'],z3.BoolVal(True)),t.target)
                initialized=False
            else:new[cell]=TypedTerm(z3.IntVal(0),t,z3.BoolVal(True));initialized=obj.zeroed
            new[flag]=TypedTerm(z3.IntVal(int(initialized)),boolean,z3.BoolVal(True))
        return new

    def location(self,node,env):
        o=self.owner;t=self.field_type(node);obj,base=o.pointer(node.name,env)
        if obj is None:
            # A synthetic dead field preserves guarded lazy expression semantics.
            proxy=Object('null-field',t,z3.IntVal(1),False,False,[],[],'')
            return proxy,TypedTerm(z3.IntVal(0),base.type,z3.BoolVal(False))
        if not isinstance(obj.type,StructType):raise SMTGraphError('Record member base type mismatch')
        cell,flag=obj.members[node.field.name]
        proxy=Object(obj.name+'.'+node.field.name,t,z3.IntVal(1),False,obj.zeroed,[cell],[flag],obj.alive)
        return proxy,TypedTerm(z3.IntVal(0),base.type,z3.And(base.safe,base.value==0))
