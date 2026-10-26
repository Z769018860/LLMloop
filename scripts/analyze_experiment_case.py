"""One API experiment in a fresh interpreter/SMT context; no success coercion."""
import json
import sys
from llmloop.api import analyze_request

if __name__=='__main__':
    request=json.load(sys.stdin)
    print(json.dumps(analyze_request(request),ensure_ascii=False))
