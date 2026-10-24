"""JSON-compatible in-process API for editors, notebooks and service adapters."""
from __future__ import annotations
from .smt_spath import SMTPathGraph, SMTGraphError
from .bounded import verify_bounded


def analyze_request(request: dict) -> dict:
    """Analyze IR or bounded C memory source; never invokes a remote model.

    The host owns transport, authentication and process isolation. Errors are
    returned as data. Resource limits are validated by the underlying engines.
    """
    try:
        if not isinstance(request, dict):raise SMTGraphError('Request must be an object')
        allowed = {'ir', 'source', 'function', 'parameter_bounds', 'max_unroll',
                   'max_paths', 'whole_function', 'invariants', 'verify_steps', 'assertion', 'ranking', 'synthesize_ranking', 'frontend', 'int_bits', 'parameter_mins', 'inputs', 'memory_layout'}
        if set(request)-allowed:raise SMTGraphError('Unknown request fields: '+', '.join(sorted(set(request)-allowed)))
        if 'synthesize_ranking' in request and type(request['synthesize_ranking']) is not bool:raise SMTGraphError('synthesize_ranking must be Boolean')
        if ('ir' in request) == ('source' in request):raise SMTGraphError('Provide exactly one of ir or source')
        if 'source' in request:
            from .memory_frontend import translate_memory_c
            if not isinstance(request['source'], str):raise SMTGraphError('source must be a string')
            frontend=request.get('frontend','memory')
            if 'memory_layout' in request and frontend!='sweep_memory':raise SMTGraphError('memory_layout requires sweep_memory frontend')
            if frontend=='ordered_scalar':
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
            else:raise SMTGraphError('frontend must be memory, ordered_scalar, counted_memory or sweep_memory')
        else:
            if set(request) & {'frontend','int_bits','whole_function','function','parameter_bounds','max_paths','max_unroll','parameter_mins','memory_layout'}:raise SMTGraphError('Source translation options cannot be applied to an existing IR')
            obj = request['ir']
            if not isinstance(obj, dict):raise SMTGraphError('ir must be an object')
        kind=obj.get('kind')
        if kind in ('counted_memory','affine_recurrence','c_integer_expression','sweep_memory','polynomial_recurrence','c_integer_symbolic'):
            if 'ir' in request and set(request)-{'ir','inputs'}:raise SMTGraphError('Special symbolic IR accepts only ir and optional inputs')
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
