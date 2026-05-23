"""Shared sandbox helpers for user script execution."""


def _safe_builtins():
    return {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "len": len,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "list": list,
        "tuple": tuple,
        "set": set,
        "dict": dict,
        "sum": sum,
        "sorted": sorted,
        "enumerate": enumerate,
        "zip": zip,
        "any": any,
        "all": all,
        "range": range,
        "map": map,
        "filter": filter,
        "next": next,
    }


def build_script_sandbox(extra_globals=None):
    """Build a sandbox dict for exec/eval use."""
    sandbox = {
        "__builtins__": _safe_builtins(),
    }
    if extra_globals:
        sandbox.update(extra_globals)
    return sandbox
