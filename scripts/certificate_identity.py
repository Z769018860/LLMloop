"""Lossless certificate identity for scheduling independent re-checks."""
import json


def certificate_key(program, invariant):
    """Keep every atom and loop; a shared text prefix is not an identity."""
    return program, json.dumps(invariant, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
