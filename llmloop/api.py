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
                   'max_paths', 'whole_function', 'invariants', 'verify_steps', 'assertion', 'ranking', 'synthesize_ranking'}
        if set(request)-allowed:raise SMTGraphError('Unknown request fields: '+', '.join(sorted(set(request)-allowed)))
        if ('ir' in request) == ('source' in request):raise SMTGraphError('Provide exactly one of ir or source')
        if 'source' in request:
            from .memory_frontend import translate_memory_c
            if not isinstance(request['source'], str):raise SMTGraphError('source must be a string')
            obj = translate_memory_c(request['source'], function=request.get('function'),
                                     parameter_bounds=request.get('parameter_bounds'),
                                     max_unroll=request.get('max_unroll',12),
                                     max_paths=request.get('max_paths',48),
                                     whole_function=request.get('whole_function',True))
        else:
            obj = request['ir']
            if not isinstance(obj, dict):raise SMTGraphError('ir must be an object')
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
        return report
    except (SMTGraphError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'status':'UNKNOWN', 'schema_version':1, 'reason':str(exc)}
