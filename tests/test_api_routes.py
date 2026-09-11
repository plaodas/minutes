from collections import Counter

from minutes.api import app


def test_http_method_and_path_pairs_are_unique():
    route_keys = [
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    ]
    duplicates = {key: count for key, count in Counter(route_keys).items() if count > 1}

    assert duplicates == {}
