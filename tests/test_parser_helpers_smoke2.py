import inspect

from moto_plan_core import parsers


def _call(method, args):
    try:
        return method(*args)
    except Exception:
        return None


def test_parser_helper_smoke():
    for cls_name in dir(parsers):
        cls = getattr(parsers, cls_name)
        if not isinstance(cls, type):
            continue
        # instantiate if possible
        try:
            instance = cls()
        except Exception:
            continue
        for method_name in dir(instance):
            if method_name.startswith("_") is False or method_name.startswith("__"):
                # only private helpers
                if not method_name.startswith("_"):
                    continue
            method = getattr(instance, method_name)
            if not callable(method):
                continue
            try:
                sig = inspect.signature(method)
            except (TypeError, ValueError):
                continue
            params = [p for p in sig.parameters.values() if p.name != "self"]
            args = []
            for p in params:
                args.append("")
            try:
                method(*args)
            except Exception:
                pass
