"""JSON-compatible in-process API for editors, notebooks and service adapters."""
from __future__ import annotations
from .smt_spath import SMTPathGraph, SMTGraphError
from .bounded import verify_bounded


def analyze_request(request: dict) -> dict:
    """Analyze supported IR or selected C frontends; never invokes a remote model.

    The host owns transport, authentication and process isolation. Errors are
    returned as data. Resource limits are validated by the underlying engines.
    """
    try:
        if not isinstance(request, dict):raise SMTGraphError('Request must be an object')
        allowed = {'ir', 'source', 'source_file', 'clang', 'function', 'parameter_bounds', 'max_unroll',
                   'max_paths', 'whole_function', 'invariants', 'verify_steps', 'assertion', 'ranking', 'synthesize_ranking', 'frontend', 'int_bits', 'parameter_mins', 'inputs', 'memory_layout', 'abi', 'char_signed', 'closed_forms', 'loop_summaries', 'max_steps', 'allocation_failure', 'max_call_depth', 'allow_recursion'}
        if set(request)-allowed:raise SMTGraphError('Unknown request fields: '+', '.join(sorted(set(request)-allowed)))
        if 'synthesize_ranking' in request and type(request['synthesize_ranking']) is not bool:raise SMTGraphError('synthesize_ranking must be Boolean')
        if request.get('frontend')=='clang':
            if ('source' in request)==('source_file' in request):raise SMTGraphError('Clang requires exactly one source or source_file')
            if set(request)-{'source','source_file','frontend','clang','function'}:raise SMTGraphError('Invalid Clang frontend options')
            from .clang_adapter import ClangAdapter
            return {'schema_version':1,**ClangAdapter(source=request.get('source'),source_file=request.get('source_file'),function=request.get('function'),options=request.get('clang')).report()}
        if set(request)&{'source_file','clang'}:raise SMTGraphError('source_file/clang options require frontend clang')
        if ('ir' in request) == ('source' in request):raise SMTGraphError('Provide exactly one of ir or source')
        if 'source' in request:
            from .memory_frontend import translate_memory_c
            if not isinstance(request['source'], str):raise SMTGraphError('source must be a string')
            frontend=request.get('frontend','memory')
            if 'loop_summaries' in request and frontend not in ('typed_nested','typed_memory'):raise SMTGraphError('loop_summaries requires typed_nested')
            if 'closed_forms' in request and frontend not in ('guarded_scalar','typed_recurrence'):raise SMTGraphError('closed_forms requires guarded_scalar or typed_recurrence frontend')
            if (set(request)&{'abi','char_signed'}) and frontend not in ('typed_c','typed_recurrence','typed_nested','typed_memory','typed_cfg_heap','typed_cfg_calls'):raise SMTGraphError('ABI options require typed_c or typed_recurrence frontend')
            if 'memory_layout' in request and frontend!='sweep_memory':raise SMTGraphError('memory_layout requires sweep_memory frontend')
            if (set(request)&{'max_steps','allocation_failure'}) and frontend not in ('typed_cfg_heap','typed_cfg_calls'):raise SMTGraphError('CFG/heap options require typed_cfg_heap or typed_cfg_calls')
            if (set(request)&{'max_call_depth','allow_recursion'}) and frontend!='typed_cfg_calls':raise SMTGraphError('Call depth requires typed_cfg_calls')
            if frontend=='typed_cfg_calls':
                if set(request)-{'source','function','frontend','parameter_bounds','abi','char_signed','max_steps','max_paths','allocation_failure','max_call_depth','allow_recursion','inputs'}:raise SMTGraphError('Invalid CFG calls options')
                from .typed_cfg_calls import TypedCFGCalls
                return {'schema_version':1,**TypedCFGCalls(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_steps=request.get('max_steps',128),max_paths=request.get('max_paths',48),allocation_failure=request.get('allocation_failure',True),max_call_depth=request.get('max_call_depth',3),allow_recursion=request.get('allow_recursion',False)).report(request.get('inputs'))}
            elif frontend=='typed_cfg_heap':
                if set(request)-{'source','function','frontend','parameter_bounds','abi','char_signed','max_steps','max_paths','allocation_failure','inputs'}:raise SMTGraphError('Invalid CFG heap options')
                from .typed_cfg_heap import TypedCFGHeap
                return {'schema_version':1,**TypedCFGHeap(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_steps=request.get('max_steps',128),max_paths=request.get('max_paths',48),allocation_failure=request.get('allocation_failure',True)).report(request.get('inputs'))}
            elif frontend=='typed_c':
                if set(request)-{'source','function','frontend','parameter_bounds','abi','char_signed','max_unroll','max_paths','inputs'}:raise SMTGraphError('Invalid typed C options')
                from .typed_c import TypedCFunction
                return {'schema_version':1,**TypedCFunction(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_unroll=request.get('max_unroll',12),max_paths=request.get('max_paths',48)).report(request.get('inputs'))}
            elif frontend=='private_allocations':
                if set(request)-{'source','function','frontend','parameter_mins','inputs'}:raise SMTGraphError('Private allocation fold accepts mathematical source/count domains only')
                from .private_allocations import PrivateAllocations
                return {'schema_version':1,**PrivateAllocations(request['source'],function=request.get('function'),parameter_mins=request.get('parameter_mins')).report(request.get('inputs'))}
            elif frontend=='typed_memory':
                if set(request)-{'source','function','frontend','parameter_bounds','loop_summaries','abi','char_signed','max_paths','inputs'}:raise SMTGraphError('Invalid typed memory options')
                from .typed_memory import TypedCMemory
                return {'schema_version':1,**TypedCMemory(request['source'],request.get('loop_summaries'),function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_paths=request.get('max_paths',48)).report(request.get('inputs'))}
            elif frontend=='typed_nested':
                if set(request)-{'source','function','frontend','parameter_bounds','loop_summaries','abi','char_signed','max_paths','inputs'}:raise SMTGraphError('Invalid typed nested options')
                from .typed_nested import TypedCNested
                return {'schema_version':1,**TypedCNested(request['source'],request.get('loop_summaries'),function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_paths=request.get('max_paths',48)).report(request.get('inputs'))}
            elif frontend=='typed_recurrence':
                if set(request)-{'source','function','frontend','parameter_bounds','closed_forms','abi','char_signed','max_paths','inputs'}:raise SMTGraphError('Invalid typed recurrence options')
                from .typed_recurrence import TypedCRecurrence
                return {'schema_version':1,**TypedCRecurrence(request['source'],request.get('closed_forms'),function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),abi=request.get('abi','LP64'),char_signed=request.get('char_signed',True),max_paths=request.get('max_paths',48)).report(request.get('inputs'))}
            elif frontend=='guarded_scalar':
                if set(request)-{'source','function','frontend','parameter_bounds','closed_forms'}:raise SMTGraphError('Invalid guarded scalar C options')
                from .periodic_c import analyze_guarded_c
                return {'schema_version':1,**analyze_guarded_c(request['source'],request.get('closed_forms'),function=request.get('function'),parameter_bounds=request.get('parameter_bounds'))}
            elif frontend=='periodic_scalar':
                if set(request)-{'source','function','frontend','parameter_bounds','invariants'}:raise SMTGraphError('Invalid periodic scalar C options')
                from .periodic_c import analyze_periodic_c
                return {'schema_version':1,**analyze_periodic_c(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),invariants=request.get('invariants'))}
            elif frontend=='memory_scan':
                if set(request)-{'source','function','frontend','parameter_bounds','int_bits','inputs'}:raise SMTGraphError('Invalid memory scan options')
                from .scan_c import translate_scan_c
                obj=translate_scan_c(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),signed_bits=request.get('int_bits'))
            elif frontend=='ordered_scalar':
                if 'whole_function' in request or 'max_unroll' in request:raise SMTGraphError('ordered_scalar supports one while loop, not whole_function or max_unroll')
                from .ordered_c import translate_ordered_c
                obj=translate_ordered_c(request['source'],function=request.get('function'),
                                        parameter_bounds=request.get('parameter_bounds'),
                                        bits=request.get('int_bits',32),max_paths=request.get('max_paths',48))
            elif frontend=='sweep_memory':
                if set(request)-{'source','function','frontend','parameter_bounds','memory_layout','int_bits','inputs'}:raise SMTGraphError('Invalid sweep_memory translation options')
                from .sweep_c import translate_sweep_c
                obj=translate_sweep_c(request['source'],function=request.get('function'),parameter_bounds=request.get('parameter_bounds'),memory_layout=request.get('memory_layout'),signed_bits=request.get('int_bits'))
            elif frontend=='counted_memory':
                if set(request)-{'source','function','frontend','parameter_mins','inputs'}:raise SMTGraphError('counted_memory accepts only source, function, parameter_mins and inputs')
                from .counted_c import translate_counted_memory_c
                obj=translate_counted_memory_c(request['source'],function=request.get('function'),parameter_mins=request.get('parameter_mins'))
            elif frontend=='memory':
                if 'int_bits' in request:raise SMTGraphError('int_bits requires ordered_scalar frontend')
                obj = translate_memory_c(request['source'], function=request.get('function'),
                                         parameter_bounds=request.get('parameter_bounds'),
                                         max_unroll=request.get('max_unroll',12),
                                         max_paths=request.get('max_paths',48),
                                         whole_function=request.get('whole_function',True))
            else:raise SMTGraphError('Unsupported source frontend')
        else:
            if set(request) & {'frontend','int_bits','whole_function','function','parameter_bounds','max_paths','max_unroll','parameter_mins','memory_layout','abi','char_signed','closed_forms','loop_summaries','max_steps','allocation_failure','max_call_depth','allow_recursion'}:raise SMTGraphError('Source translation options cannot be applied to an existing IR')
            obj = request['ir']
            if not isinstance(obj, dict):raise SMTGraphError('ir must be an object')
        kind=obj.get('kind')
        if kind in ('counted_memory','affine_recurrence','c_integer_expression','sweep_memory','polynomial_recurrence','c_integer_symbolic','linear_memory_scan','periodic_recurrence','guarded_recurrence'):
            if 'ir' in request and set(request)-{'ir','inputs'}:raise SMTGraphError('Special symbolic IR accepts only ir and optional inputs')
            if kind=='guarded_recurrence':
                from .guarded_recurrence import summarize_guarded
                return {'schema_version':1,**summarize_guarded(obj,request.get('inputs'))}
            if kind=='linear_memory_scan':
                from .linear_scan import LinearScan
                return {'schema_version':1,**LinearScan(obj).report(request.get('inputs'))}
            if kind=='sweep_memory':
                from .sweep_memory import SweepMemory
                return {'schema_version':1,**SweepMemory(obj).report(request.get('inputs'))}
            if kind=='c_integer_symbolic':
                from .symbolic_integers import SymbolicIntegers
                return {'schema_version':1,**SymbolicIntegers(obj).report(request.get('inputs'))}
            if kind=='counted_memory':
                from .unbounded_memory import UnboundedMemory
                return {'schema_version':1,**UnboundedMemory(obj).report(request.get('inputs'))}
            if 'inputs' in request:raise SMTGraphError('inputs is supported only for counted_memory or SPath IR')
            if kind=='polynomial_recurrence':
                from .polynomial_recurrence import summarize_polynomial
                return {'schema_version':1,**summarize_polynomial(obj)}
            if kind=='periodic_recurrence':
                from .periodic_recurrence import summarize_periodic
                return {'schema_version':1,**summarize_periodic(obj)}
            if kind=='affine_recurrence':
                from .recurrence import summarize_recurrence
                return {'schema_version':1,**summarize_recurrence(obj)}
            from .c_integers import evaluate_integer_request
            return {'schema_version':1,**evaluate_integer_request(obj)}
        graph = SMTPathGraph(obj)
        invariants = request.get('invariants', [])
        if not isinstance(invariants,list) or not all(isinstance(x,str) for x in invariants):
            raise SMTGraphError('invariants must be a list of strings')
        certificates = graph.certify_invariants(invariants) if invariants else []
        if 'assertion' in request and 'verify_steps' not in request:
            raise SMTGraphError('assertion requires verify_steps')
        report = {'status':'ANALYZED', 'schema_version':1, 'ir':obj,
                  'invariants':certificates, 'analysis':graph.analyze()}
        if 'verify_steps' in request:
            report['bounded_verification'] = verify_bounded(graph, request['verify_steps'],request.get('assertion'))
        if 'ranking' in request or request.get('synthesize_ranking'):
            from .ranking import verify_ranking, synthesize_ranking
            if 'ranking' in request:report['ranking']=verify_ranking(graph,request['ranking'])
            if request.get('synthesize_ranking'):report['ranking_synthesis']=synthesize_ranking(graph)
        if 'inputs' in request:report['evaluation']=graph.concrete(request['inputs'])
        return report
    except (SMTGraphError, ValueError, TypeError, KeyError, AttributeError, SyntaxError) as exc:
        return {'status':'UNKNOWN', 'schema_version':1, 'reason':str(exc)}
