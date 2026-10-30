"""Compiler-checked local integer union views, lowered to guarded word storage.

Only full-word writes and scalar reads are admitted. This is an explicit x86
little-endian representation contract, not general byte memory/type punning.
"""
import re

from .c_integers import IntegerABI
from .clang_proof import ScalarNormalizer
from .smt_spath import SMTGraphError


class UnionViewNormalizer(ScalarNormalizer):
    def __init__(self,frontend):
        super().__init__(frontend)
        triple=frontend['target']['triple']
        model='LLP64' if '-windows-' in triple else 'LP64' if triple.startswith('x86_64-') else 'ILP32'
        char_signed='-funsigned-char' not in frontend['effective_flags']
        self.union_abi=IntegerABI(model,char_signed)
        self.union_records={r['id']:r for r in frontend.get('record_definitions',[])}
        self.union_schemas={};self.union_objects={};self.union_views=[]

    def union_record(self,value):
        text=value.get('desugaredQualType',value.get('qualType','')) if isinstance(value,dict) else value
        if not isinstance(text,str) or re.search(r'[*\[\]]|\b(const|volatile|restrict|_Atomic)\b',text):return None
        aliases=[n for n in self.frontend.get('typedefs',[]) if n['name']==text or n['type'].get('qualType')==text]
        ids={i for a in aliases for i in a.get('record_ids',[]) if i in self.union_records and self.union_records[i].get('tagUsed')=='union'}
        if text.startswith('union '):ids.update(r['id'] for r in self.union_records.values() if r.get('tagUsed')=='union' and r.get('name')==text[6:])
        if len(ids)>1:raise SMTGraphError('Ambiguous Clang union definition')
        return self.union_records[next(iter(ids))] if ids else None

    def union_layout(self,record):
        kind=record['tagUsed'];name=record.get('name');loc=record.get('loc',{})
        if any(k in loc for k in ('expansionLoc','spellingLoc')):raise SMTGraphError('Macro-located union views unsupported')
        if name:candidates=[r for r in self.frontend['record_layouts'] if r['name']==kind+' '+name]
        else:
            line=record.get('layout_line') or loc.get('line');column=loc.get('col')
            if type(line) is not int or type(column) is not int:raise SMTGraphError('Anonymous union view source location unavailable')
            suffix=':'+str(line)+':'+str(column)+')'
            candidates=[r for r in self.frontend['record_layouts'] if r['name'].startswith(kind+' ') and r['name'].endswith(suffix)]
        if len(candidates)!=1:raise SMTGraphError('Unique Clang union/struct view layout required')
        return candidates[0]

    def union_schema(self,record):
        if record['id'] in self.union_schemas:return self.union_schemas[record['id']]
        if not self.frontend['target']['data_layout'].startswith('e-'):raise SMTGraphError('Union views require compiler-confirmed little endian')
        if len(self.union_schemas)>=8:raise SMTGraphError('Union view type budget is 8')
        leaves={};checks=[]
        def build(current,prefix=(),ids=(),depth=0):
            if depth>2 or current.get('tagUsed') not in ('union','struct') or depth and current['tagUsed']!='struct':raise SMTGraphError('Union views allow at most two nested struct levels')
            children=current.get('inner',[])
            if any(n.get('kind') not in ('FieldDecl','RecordDecl','FullComment') for n in children):raise SMTGraphError('Attributed/packed union views unsupported')
            fields=[n for n in children if n.get('kind')=='FieldDecl']
            if not 1<=len(fields)<=8:raise SMTGraphError('Union views require 1..8 fields per record')
            offset=0;alignment=1;flatten=[];seen=set()
            inline={n.get('range',{}).get('begin',{}).get('offset'):n for n in children if n.get('kind')=='RecordDecl' and n.get('completeDefinition')}
            for field in fields:
                name=field.get('name','');path=prefix+(name,);field_ids=ids+(field['id'],)
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) or name in seen or field.get('isBitfield') or field.get('inner'):raise SMTGraphError('Union view fields must be named, unqualified and non-bitfield')
                seen.add(name);text=field['type'].get('desugaredQualType',field['type']['qualType'])
                nested=inline.get(field.get('range',{}).get('begin',{}).get('offset'))
                if nested is not None:
                    nested=self.union_records.get(nested['id'],nested)
                    size,align,sub=build(nested,path,field_ids,depth+1)
                else:
                    if re.search(r'\b(const|volatile|_Atomic|_Bool|char)\b',text) or any(c in text for c in '*[]'):raise SMTGraphError('Union views require non-char integer leaves')
                    ctype=super(UnionViewNormalizer,self).type(field['type'])
                    parts=ctype.split();base='short' if 'short' in parts else 'long long' if parts.count('long')==2 else 'long' if 'long' in parts else 'int'
                    words=('unsigned ' if 'unsigned' in parts else 'signed ')+base
                    if words not in self.union_abi.types:raise SMTGraphError('Unsupported union integer leaf type')
                    t=self.union_abi.types[words];size=t.bits//8;align=min(size,4 if self.union_abi.model=='ILP32' else 8)
                    if size not in (2,4,8):raise SMTGraphError('Union views require 16/32/64-bit integer leaves')
                    leaves[path]={'type':ctype,'bits':t.bits,'field_ids':field_ids,'offset':0}
                    sub=[]
                position=0 if current['tagUsed']=='union' else (offset+align-1)//align*align
                if current['tagUsed']=='struct' and position!=offset:raise SMTGraphError('Padded struct union views unsupported')
                for path_key,leaf in leaves.items():
                    if path_key[:len(path)]==path:leaf['offset']+=position
                flatten.append((name,position,1))
                flatten.extend((n,o+position,d+1) for n,o,d in sub)
                offset=max(offset,size) if current['tagUsed']=='union' else position+size;alignment=max(alignment,align)
            size=(offset+alignment-1)//alignment*alignment
            if current['tagUsed']=='struct' and size!=offset:raise SMTGraphError('Tail-padded struct union views unsupported')
            layout=self.union_layout(current)
            actual=[(m['declaration'].split()[-1],m['offset_bytes'],m.get('depth')) for m in layout['members']]
            if any('bit_range' in m for m in layout['members']) or actual!=flatten or layout['size_bytes']!=size or layout['alignment_bytes']!=alignment:raise SMTGraphError('Clang union view layout differs from the integer model')
            checks.append({'compiler':layout,'model':{'size_bytes':size,'alignment_bytes':alignment,'members':flatten}})
            return size,alignment,flatten
        size,alignment,unused=build(record)
        if size not in (4,8) or not any(len(path)==1 and leaf['bits']==size*8 for path,leaf in leaves.items()):raise SMTGraphError('Union views require a full 32/64-bit integer member')
        if len(leaves)>16 or any(v['offset']*8+v['bits']>size*8 for v in leaves.values()):raise SMTGraphError('Union view leaf budget/layout exceeded')
        schema={'record_id':record['id'],'compiler_layout':self.union_layout(record)['name'],'size_bytes':size,'alignment_bytes':alignment,'leaves':leaves,'layout_checks':checks}
        self.union_schemas[record['id']]=schema;return schema

    def union_access(self,node):
        path=[];ids=[]
        while True:
            while node.get('kind')=='ParenExpr' and len(node.get('inner',[]))==1:node=node['inner'][0]
            if node.get('kind')!='MemberExpr' or node.get('isArrow') or len(node.get('inner',[]))!=1:break
            path.insert(0,node.get('name'));ids.insert(0,node.get('referencedMemberDecl'));node=node['inner'][0]
        if node.get('kind')!='DeclRefExpr' or node.get('referencedDecl',{}).get('id') not in self.union_objects:return None
        view=self.union_objects[node['referencedDecl']['id']];key=tuple(path)
        if key not in view['schema']['leaves'] or tuple(ids)!=view['schema']['leaves'][key]['field_ids']:raise SMTGraphError('Union access requires a validated scalar leaf path')
        return view,view['schema']['leaves'][key]

    def decl(self,node):
        record=self.union_record(node.get('type',{}))
        if record is None:return super().decl(node)
        if node.get('storageClass') or node.get('tls') or node.get('inner'):raise SMTGraphError('Union views require uninitialized automatic local declarations')
        if len(self.union_objects)>=8:raise SMTGraphError('Union view local object budget is 8')
        schema=self.union_schema(record);storage=self.fresh('union_word');flag=self.fresh('union_initialized')
        word='unsigned int' if schema['size_bytes']==4 else 'unsigned long long'
        self.union_objects[node['id']]={'schema':schema,'storage':storage,'flag':flag,'word':word}
        self.union_views.append({'source':self.names[node['id']],'storage':storage,'initialized_flag':flag,'compiler_layout':schema['compiler_layout'],'record_id':schema['record_id'],'layout_checks':schema['layout_checks'],
                                 'size_bytes':schema['size_bytes'],'alignment_bytes':schema['alignment_bytes'],
                                 'members':{'.'.join(k):{a:b for a,b in v.items() if a!='field_ids'} for k,v in schema['leaves'].items()}})
        return word+' '+storage+' = 0; int '+flag+' = 0'

    def expr(self,node):
        if node.get('kind')=='MemberExpr':
            access=self.union_access(node)
            if access:
                view,leaf=access;t=leaf['type'];value='(('+t+')('+view['storage']+' >> '+str(8*leaf['offset'])+'))'
                return '(('+t+')('+value+' / (('+t+')'+view['flag']+')))'
        if node.get('kind')=='DeclRefExpr' and node.get('referencedDecl',{}).get('id') in self.union_objects:raise SMTGraphError('Union values/addresses may not escape or be copied')
        if node.get('kind')=='UnaryExprOrTypeTraitExpr' and node.get('name')=='sizeof':
            children=node.get('inner',[]);t=node.get('argType') or (children[0].get('type') if len(children)==1 else {})
            record=self.union_record(t)
            if record is not None:return '(('+self.type(node['type'])+')'+str(self.union_schema(record)['size_bytes'])+')'
        return super().expr(node)

    def action(self,node):
        children=node.get('inner',[])
        if node.get('kind') in ('BinaryOperator','CompoundAssignOperator') and children:
            access=self.union_access(children[0])
            if access:
                view,leaf=access
                if node.get('opcode')!='=' or len(children)!=2 or leaf['offset'] or leaf['bits']!=view['schema']['size_bytes']*8:raise SMTGraphError('Union views admit only full-word simple stores')
                return '('+view['storage']+' = (('+view['word']+') (('+leaf['type']+')('+self.expr(children[1])+'))), '+view['flag']+' = 1)'
        return super().action(node)

    def stmt(self,node):
        if node.get('kind')=='ForStmt' and node.get('inner'):
            init=node['inner'][0]
            if init.get('kind')=='DeclStmt' and any(self.union_record(n.get('type',{})) is not None for n in init.get('inner',[]) if n.get('kind')=='VarDecl'):raise SMTGraphError('Union declaration in for initializer unsupported')
        return super().stmt(node)
