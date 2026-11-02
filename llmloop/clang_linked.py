"""Closed-component binding of independently compiled C translation units.

This is a checked source bridge, not a native linker or assumed external model.
Each function is normalized in its own compiler/type/declaration context. Local
Clang AST IDs are never merged; static function symbols get hygienic TU names.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from .clang_adapter import ClangAdapter
from .smt_spath import SMTGraphError
from .clang_parameters import checked_pointer_parameter


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def char_signed(front):
    result=True
    for flag in front['effective_flags']:
        if flag in ('-funsigned-char','-fsigned-char'):result=flag=='-fsigned-char'
    return result


class LinkedClangProject:
    def __init__(self,source,source_file,options):
        self.source,self.source_file=source,source_file
        self.options=copy.deepcopy(options)
        self.units=[];self.snapshots={};self.certificate={}

    def check_snapshot(self):
        for path,sha in self.snapshots.items():
            if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:
                raise SMTGraphError('Linked translation-unit source changed during analysis: '+path)

    def report(self):
        failure={'status':'UNKNOWN','frontend':'clang_proof','c_overflow_verified':False,
            'memory_safety_verified':False,'termination_proved':False}
        try:
            linked=self.options.pop('linked_sources')
            if not isinstance(linked,list) or not 1<=len(linked)<=7:
                raise SMTGraphError('clang.linked_sources requires one to seven additional translation units')
            requests=[(self.source,self.source_file,self.options)]
            for item in linked:
                if isinstance(item,str):item={'source_file':item}
                if (not isinstance(item,dict) or set(item)-{'source_file','command_index'}
                        or not isinstance(item.get('source_file'),str) or not item['source_file'] or '\0' in item['source_file']):
                    raise SMTGraphError('Each linked source requires source_file and optional command_index')
                options={k:v for k,v in self.options.items() if k!='command_index'}
                if 'command_index' in item:options['command_index']=item['command_index']
                requests.append((None,item['source_file'],options))
            for _,path,_ in requests:
                if path is None:continue
                resolved=str(Path(path).resolve())
                if resolved in self.snapshots:raise SMTGraphError('Duplicate linked translation-unit source')
                if not Path(resolved).is_file() or Path(resolved).stat().st_size>1024*1024:
                    raise SMTGraphError('Linked source missing or exceeds 1 MiB')
                self.snapshots[resolved]=hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
            for text,path,options in requests:
                front=ClangAdapter(text,path,None,options).report()
                self.units.append(front)
                if front['status']!='CLANG_FRONTEND_READY':
                    return {**failure,'reason':'Linked Clang ingestion failed: '+front.get('reason',''),
                        'translation_units':self.units}
            primary=self.units[0]
            for front in self.units[1:]:
                if (front['target']!=primary['target'] or char_signed(front)!=char_signed(primary)
                        or front['compiler']['version']!=primary['compiler']['version']):
                    raise SMTGraphError('Linked units require identical compiler target/layout and char semantics')
            if sum(f['ast_nodes'] for f in self.units)>250000 or sum(len(f['functions']) for f in self.units)>128:
                raise SMTGraphError('Linked project exceeds aggregate 250000 AST nodes or 128 function definitions')
            if sum(len(f['llvm_ir'].encode()) for f in self.units)>16*1024*1024:
                raise SMTGraphError('Linked LLVM export exceeds aggregate 16 MiB')
            self.check_snapshot()
            self.front={**primary,'linked_translation_units':self.units,
                'input_consistency':'all supplied main source files checked unchanged across project ingestion and proof; included headers/environment must remain stable',
                'proof_boundary':'closed supplied function component; Clang/source binding trusted; no assumed external semantics, native linker, dynamic interposition or whole C/LLVM proof'}
            return self.front
        except (SMTGraphError,OSError,ValueError,TypeError,KeyError) as exc:
            return {**failure,'reason':str(exc),'translation_units':self.units}

    def normalize(self,function,static_array_contracts=False):
        from .clang_proof import nodes, check_parameter_attributes, check_typedef_attributes
        from .clang_memory_proof import MemoryNormalizer,BUILTINS
        from .clang_bit_builtins import BIT_BUILTINS,BitBuiltinModels
        # Keep every per-TU declaration/type context separate, including IDs
        # that happen to have the same pointer spelling in different processes.
        units=copy.deepcopy(self.units)
        tables=[];roots=[];internal=[];definitions={};external={};used=set()
        for index,front in enumerate(units):
            table={n['id']:n for n in front.get('external_function_declarations',[])}
            table.update({f['ast']['id']:f['ast'] for f in front['functions']})
            tables.append(table)
            def canonical(key):
                seen=set()
                while key in table and table[key].get('previousDecl'):
                    if key in seen:raise SMTGraphError('Cyclic Clang function redeclaration identity')
                    seen.add(key);key=table[key]['previousDecl']
                return key
            local_roots={key:canonical(key) for key in table};roots.append(local_roots)
            internal.append({local_roots[n['id']] for n in table.values() if n.get('storageClass')=='static'})
            for fn in front['functions']:
                name=fn['name'];node=fn['ast']
                if name in BUILTINS or name in BIT_BUILTINS:
                    raise SMTGraphError('Linked user definitions of modeled allocator/bit builtins unsupported')
                key=(index,local_roots[node['id']])
                if key in definitions:raise SMTGraphError('Duplicate linked definition identity')
                definitions[key]=fn
                if key[1] not in internal[index]:
                    if name in external:raise SMTGraphError('Multiple external function definitions in supplied units: '+name)
                    external[name]=key
            for fn in front['functions']:
                used.update(n['name'] for n in nodes(fn['ast']) if n.get('name'))
            used.update(n.get('name') for n in table.values() if n.get('name'))
        primary=[(key,fn) for key,fn in definitions.items() if key[0]==0 and (function is None or fn['name']==function)]
        if len(primary)!=1:raise SMTGraphError('Select one defined entry in the primary translation unit')
        entry_key,entry_fn=primary[0]
        source_entry=entry_fn['name']
        emitted={};renames=[];array_parameters={};static_minima={}
        for key,fn in definitions.items():
            name=fn['name']
            if key[1] in internal[key[0]]:
                fresh='__clang_tu'+str(key[0])+'_'+name
                while fresh in used:fresh+='_'
                used.add(fresh);renames.append({'unit':key[0],'source':name,'normalized':fresh});name=fresh
            emitted[key]=name

        def scalar_type(value,index,seen=()):
            text=value.get('desugaredQualType',value.get('qualType','')) if isinstance(value,dict) else value
            if not isinstance(text,str):raise SMTGraphError('Linked integer/pointer type missing')
            text=' '.join(text.split())
            if re.search(r'\b(const|volatile|restrict|_Atomic)\b',text) or any(c in text for c in '[]()'):
                raise SMTGraphError('Linked interfaces require unqualified integer/literal pointer types')
            base=text.rstrip('* ').strip();suffix=text[len(base):]
            if suffix.replace('*','').strip():raise SMTGraphError('Unsupported linked type')
            stars=suffix.count('*')
            if stars>3:raise SMTGraphError('Linked pointer indirection budget is three')
            aliases={}
            for alias in units[index].get('typedefs',[]):
                aliases.setdefault(alias['name'],set()).add(alias['type'].get('desugaredQualType',alias['type'].get('qualType','')))
            if base in aliases:
                if base in seen or len(aliases[base])!=1:raise SMTGraphError('Ambiguous/cyclic linked typedef')
                result=scalar_type(next(iter(aliases[base])),index,seen+(base,))+' *'*stars
            else:
                from .clang_proof import INTEGER
                if base=='void' and not stars:return 'void'
                if re.fullmatch(r'struct [A-Za-z_][A-Za-z0-9_]*',base):
                    if not stars:raise SMTGraphError('Linked by-value struct interfaces unsupported')
                    record_types.require(index,base.split()[1])
                    return base+' *'*stars
                if base not in INTEGER:raise SMTGraphError('Linked interfaces require integers or admitted integer/struct pointers')
                if base in ('char','signed char','unsigned char','_Bool'):canonical=base
                else:
                    parts=base.split();width='short' if 'short' in parts else 'long long' if parts.count('long')==2 else 'long' if 'long' in parts else 'int'
                    canonical=('unsigned ' if 'unsigned' in parts else 'signed ')+width
                result=canonical+' *'*stars
            if result.count('*')>3:raise SMTGraphError('Linked pointer indirection budget is three')
            return result

        from .clang_linked_records import LinkedRecordTypes
        record_types=LinkedRecordTypes(units,scalar_type)
        self.record_types=record_types

        def type_signature(value,index):
            text=value.get('desugaredQualType',value.get('qualType',''))
            match=re.fullmatch(r'(.+?)\s*\((.*)\)',text)
            if not match or not match[2].strip() or '...' in match[2]:
                raise SMTGraphError('Linked functions require nonvariadic prototypes, including explicit void')
            parts=[] if match[2].strip()=='void' else match[2].split(',')
            parameters=tuple(scalar_type(part.strip(),index) for part in parts)
            if 'void' in parameters:raise SMTGraphError('Invalid linked void parameter')
            return scalar_type(match[1].strip(),index),parameters

        def signature(node,index,contract_target=None):
            check_typedef_attributes(units[index],node)
            if any(n.get('kind') not in ('ParmVarDecl','CompoundStmt','FullComment') for n in node.get('inner',[])):
                raise SMTGraphError('Attributed linked function declarations/definitions unsupported')
            if node.get('inline') and roots[index].get(node['id']) not in internal[index]:
                raise SMTGraphError('External inline linkage is outside the closed linked component')
            params=[p for p in node.get('inner',[]) if p.get('kind')=='ParmVarDecl']
            check_parameter_attributes(params)
            canonical=type_signature(node.get('type',{}),index)
            if canonical[1]!=tuple(scalar_type(p['type'],index) for p in params):
                raise SMTGraphError('Linked function type and parameter declaration metadata differ')
            # Adjusted pointer types erase array bounds/entry effects. Check
            # every original caller/provider declaration, not only definitions.
            metadata={d['id']:d for d in units[index].get('function_parameter_declarations',[])}
            for position,param in enumerate(params):
                resolved=scalar_type(param['type'],index)
                if '*' not in resolved:continue
                raw=metadata.get(node['id'],{}).get('parameter_spellings',{}).get(param['id'],'')
                adjustment=checked_pointer_parameter(param,raw,resolved,lambda value:scalar_type(value,index),static_array_contracts)
                if adjustment is not None:
                    array_parameters[(index,node['id'],param['id'])]={'unit':index,
                        'function':node['name'],'declaration_id':node['id'],'parameter_index':position,**adjustment}
                    if contract_target is not None and 'minimum_extent_required' in adjustment:
                        requirements=static_minima.setdefault(contract_target,{})
                        requirements[position]=max(requirements.get(position,0),adjustment['minimum_extent_required'])
            return canonical

        selected=set();pending=[entry_key];bindings=[];checked=set();targets={}
        def resolve(index,ref):
            identifier=ref.get('id');name=ref.get('name')
            if identifier not in roots[index]:raise SMTGraphError('Linked call declaration identity missing')
            key=(index,roots[index][identifier])
            if key[1] in internal[index] and key not in definitions:
                raise SMTGraphError('Undefined internal function cannot bind across translation units')
            if key not in definitions:key=external.get(name)
            if key is None:return None
            declaration=tables[index][identifier];provider=definitions[key]['ast']
            if declaration.get('name')!=name or type_signature(ref.get('type',{}),index)!=signature(declaration,index):
                raise SMTGraphError('Linked call reference and declaration metadata differ')
            expected=signature(declaration,index,emitted[key]);actual=signature(provider,key[0],emitted[key])
            if expected!=actual:raise SMTGraphError('Linked caller/provider function types differ: '+str(name))
            # Every redeclaration in the caller's chain contributes obligations.
            for unit,identity in ((index,roots[index][identifier]),key):
                for ident,root in roots[unit].items():
                    if root==identity and signature(tables[unit][ident],unit,emitted[key])!=actual:
                        raise SMTGraphError('Incompatible linked redeclaration chain')
            marker=(index,identifier,key)
            if marker not in checked:
                checked.add(marker);bindings.append({'caller_unit':index,'declaration_id':identifier,
                    'callee':name,'provider_unit':key[0],'provider_definition_id':provider['id'],
                    'normalized_callee':emitted[key],'canonical_signature':[actual[0],list(actual[1])],
                    'declaration_checked':True,'body_is_supplied_source':True})
            return key
        while pending:
            key=pending.pop()
            if key in selected:continue
            selected.add(key)
            if len(selected)>16:raise SMTGraphError('Linked call proof supports at most sixteen reachable functions')
            signature(definitions[key]['ast'],key[0],emitted[key])
            for node in nodes(definitions[key]['ast']):
                if node.get('kind')!='DeclRefExpr' or node.get('referencedDecl',{}).get('kind')!='FunctionDecl':continue
                ref=node['referencedDecl']
                if ref.get('name') in BUILTINS or ref.get('name') in BIT_BUILTINS:
                    if ref.get('id') not in roots[key[0]] or roots[key[0]][ref['id']] in internal[key[0]]:
                        raise SMTGraphError('Modeled linked builtin requires external compiler declaration')
                    continue
                target=resolve(key[0],ref)
                targets[(key[0],ref['id'])]=target
                if target is not None:pending.append(target)
        # Rename only function identities. Member/tag/value names are untouched.
        for index,front in enumerate(units):
            names={identifier:emitted[(index,root)] for identifier,root in roots[index].items() if (index,root) in definitions}
            for fn in front['functions']:
                for node in nodes(fn['ast']):
                    if node.get('kind')=='FunctionDecl' and node.get('id') in names:node['name']=names[node['id']]
                    if node.get('kind')=='DeclRefExpr' and node.get('referencedDecl',{}).get('kind')=='FunctionDecl':
                        ref=node['referencedDecl']
                        if ref.get('name') in BUILTINS or ref.get('name') in BIT_BUILTINS:continue
                        target=targets.get((index,ref.get('id'))) if (index,roots[index].get(fn['ast']['id'])) in selected else None
                        if target is not None:ref['name']=emitted[target]
                fn['name']=fn['ast']['name']
            for declaration in front.get('function_parameter_declarations',[]):
                if declaration['id'] in names:declaration['name']=names[declaration['id']]
        shared_models={};models_by_unit={};normalizers=[];sources=[]
        callable_names={emitted[key] for key in selected}
        for key in sorted(selected,key=lambda k:emitted[k]):
            index=key[0];front=units[index]
            if index not in models_by_unit:
                models=BitBuiltinModels(front,used);models.used=used;models.models=shared_models;models_by_unit[index]=models
            normalizer=MemoryNormalizer({**front,'functions':[definitions[key]]},callable_names,models_by_unit[index],static_array_contracts)
            source=normalizer.source()
            if normalizer.union_views:
                raise SMTGraphError('Linked union views are not yet admitted')
            for tag in sorted(normalizer.used_records):record_types.require(index,tag)
            normalizers.append(normalizer);sources.append(source)
        sources.extend(m['source'] for m in shared_models.values())
        prototypes=[s.split('{',1)[0].strip()+';' for s in sources];external_prototypes={}
        for normalizer in normalizers:
            for name,prototype in normalizer.external_prototypes.items():
                if name in external_prototypes and external_prototypes[name]!=prototype:
                    raise SMTGraphError('Conflicting unresolved linked external declarations')
                external_prototypes[name]=prototype
        normalized='\n'.join(list(external_prototypes.values())+prototypes+sources)
        if len(normalized)>200000:raise SMTGraphError('Linked normalized source exceeds 200000 characters')
        self.certificate={'method':'checked closed-component Clang function binding across translation units',
            'entry':{'source':source_entry,'unit':0,'normalized':emitted[entry_key]},
            'units':[{'index':i,'source':f['source'],'target':f['target'],'effective_flags':f['effective_flags'],
                'compilation_database':f['compilation_database'],'llvm_ir_sha256':f['llvm_ir_sha256'],
                'function_ast_sha256':digest([n['ast'] for n in f['functions']]),
                **({'preprocessed_snapshot_sha256':f['preprocessing']['sha256']} if 'preprocessing' in f else {})} for i,f in enumerate(self.units)],
            'bindings':bindings,'static_function_renames':renames,'reachable_functions':[emitted[k] for k in sorted(selected)],
            'caller_provider_types_checked':True,'per_unit_declaration_contexts_preserved':True,
            'source_snapshots_checked':True,'closed_world_function_binding':True,'external_semantics_assumed':False,
            'dynamic_interposition_modeled':False,'general_linker_or_C_support':False,
            'normalized_source_sha256':hashlib.sha256(normalized.encode()).hexdigest(),
            **({'array_parameter_adjustments':list(array_parameters.values())} if array_parameters else {}),
            **({'static_array_contracts':static_minima} if static_minima else {}),
            **({'record_compatibility':record_types.certificate} if record_types.schemas else {})}
        self.check_snapshot()
        self.static_array_contracts=static_minima
        return normalized,normalizers,emitted[entry_key]
