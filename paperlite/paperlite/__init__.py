__all__ = [
    "Paper",
    "enrich_paper",
    "enrich_papers",
    "export",
    "translate_paper",
]

_EXPORTS = {
    "Paper": ("paperlite.models", "Paper"),
    "enrich_paper": ("paperlite.core", "enrich_paper"),
    "enrich_papers": ("paperlite.core", "enrich_papers"),
    "export": ("paperlite.core", "export"),
    "translate_paper": ("paperlite.translation", "translate_paper"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'paperlite' has no attribute {name!r}")
    from importlib import import_module

    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
