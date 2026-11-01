"""Conservative cross-TU named-struct compatibility, not tag/size guessing.

Only the existing naturally laid out finite-record model is admitted. All used
same-tag definitions must match ordered names and canonical C member types,
including recursive pointer edges; all compiler layouts must agree. Each unit
is then checked separately against the successful proof model's record layout.
"""
import hashlib
import json
import re

from .smt_spath import SMTGraphError


class LinkedRecordTypes:
    def __init__(self, units, canonical_type):
        self.units = units
        self.canonical_type = canonical_type
        from .clang_proof import nodes
        self.function_scope_records = []
        for unit in units:
            functions = [f['ast'] for f in unit['functions']] + unit.get('external_function_declarations', [])
            self.function_scope_records.append({n.get('id') for function in functions for n in nodes(function)
                                               if n.get('kind') == 'RecordDecl' and n.get('completeDefinition')})
        self.active = set()
        self.complete = set()
        self.schemas = {}
        self.discovered_tags = set()
        self.unit_tags = {}
        self.certificate = {'method': 'ordered canonical named-struct graph compatibility plus per-unit Clang/model layouts',
                            'records': self.schemas, 'proof_model_layouts_checked': False,
                            'by_value_records_supported': False, 'unions_supported': False}

    def require(self, unit, tag):
        key = (unit, tag)
        if key in self.active or key in self.complete:
            return
        self.discovered_tags.add(tag)
        if len(self.discovered_tags)>8:
            raise SMTGraphError('Linked record graph budget is eight tags')
        front = self.units[unit]
        definitions = [r for r in front.get('record_definitions', []) if r.get('name') == tag]
        if len(definitions) != 1 or definitions[0].get('tagUsed') != 'struct':
            raise SMTGraphError('Linked records require one complete named struct definition per used unit: ' + tag)
        record = definitions[0]
        if record['id'] in self.function_scope_records[unit]:
            raise SMTGraphError('Linked record definitions must have file scope: ' + tag)
        fields = record.get('inner', [])
        if not 1 <= len(fields) <= 8:
            raise SMTGraphError('Linked records require one to eight unqualified named scalar/pointer fields')
        self.active.add(key)
        members = []
        for field in fields:
            name = field.get('name', '')
            if (field.get('kind') != 'FieldDecl' or field.get('isBitfield') or field.get('inner')
                    or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)):
                raise SMTGraphError('Attributed/anonymous/bitfield linked records unsupported')
            value = self.canonical_type(field.get('type', {}), unit)
            if value == 'void' or value.startswith('struct ') and '*' not in value:
                raise SMTGraphError('Linked record members require integers or admitted data pointers')
            members.append({'name': name, 'type': value})
        if len({m['name'] for m in members}) != len(members):
            raise SMTGraphError('Duplicate linked record member')
        candidates = [r for r in front.get('record_layouts', []) if r.get('name') == 'struct ' + tag]
        if len(candidates) != 1:
            raise SMTGraphError('Unique compiler layout required for linked record: ' + tag)
        layout = candidates[0]
        observed = layout.get('members', [])
        names = [m.get('declaration', '').split()[-1].lstrip('*') if m.get('declaration', '').split() else '' for m in observed]
        if (names != [m['name'] for m in members] or any(m.get('depth') != 1 or 'bit_range' in m for m in observed)
                or any(type(m.get('offset_bytes')) is not int or m['offset_bytes'] < 0 for m in observed)
                or any(type(layout.get(k)) is not int or layout[k] <= 0 for k in ('size_bytes', 'alignment_bytes'))):
            raise SMTGraphError('Linked record compiler member layout metadata differs from declaration')
        profile = {'size_bytes': layout['size_bytes'], 'alignment_bytes': layout['alignment_bytes'],
                   'member_offsets': [[m['name'], o['offset_bytes']] for m, o in zip(members, observed)]}
        prior = self.schemas.get(tag)
        if prior is not None and (prior['members'] != members or prior['compiler_layout'] != profile):
            raise SMTGraphError('Incompatible linked record definitions/layouts: ' + tag)
        if prior is None:
            prior = self.schemas[tag] = {'members': members, 'compiler_layout': profile, 'definitions': []}
            if len(self.schemas) > 8:
                raise SMTGraphError('Linked record graph budget is eight tags')
        prior['definitions'].append({'unit': unit, 'record_id': record['id'], 'definition_scope': 'file',
                                    'ast_sha256': hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()})
        self.unit_tags.setdefault(unit, set()).add(tag)
        self.active.remove(key)
        self.complete.add(key)

    def check_model(self, result, tags):
        from .clang_memory_proof import check_record_layouts
        if set(self.schemas) != set(tags):
            raise SMTGraphError('Linked record emission and compatibility graph differ')
        by_unit = {}
        merged = {}
        for index, used in sorted(self.unit_tags.items()):
            correspondence = check_record_layouts(self.units[index], result, used)
            by_unit[str(index)] = correspondence
            for tag, profile in correspondence.items():
                if tag in merged and merged[tag] != profile:
                    raise SMTGraphError('Linked compiler/model record layout mismatch: ' + tag)
                merged[tag] = profile
        self.certificate['proof_model_layouts_by_unit'] = by_unit
        self.certificate['proof_model_layouts_checked'] = True
        return merged
