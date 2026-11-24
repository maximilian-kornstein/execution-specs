from typing import Any, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

class Memory:
    def __init__(self, location: str, verbose: int = ...) -> None: ...
    def cache(self, func: _F) -> _F: ...
