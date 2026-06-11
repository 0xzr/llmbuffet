"""freellmpool — pool free-tier LLM APIs behind one OpenAI-compatible endpoint.

Public API:

    from freellmpool import Pool

    pool = Pool.from_default_config()
    reply = pool.ask("Explain CAP theorem in one sentence.")
    print(reply.text)
"""

from .errors import (
    AllProvidersExhausted,
    ContextWindowExceeded,
    FreeLLMPoolError,
    NoProvidersConfigured,
)
from .metrics import Metrics
from .models import EmbedReply, Model, Provider, Reply
from .plugins import register_adapter, register_provider
from .router import Pool

__version__ = "0.11.1"


def __getattr__(name: str):
    # Lazy so importing freellmpool never imports the async stack (httpx.AsyncClient)
    # unless someone actually asks for AsyncPool.
    if name == "AsyncPool":
        from .aio import AsyncPool

        return AsyncPool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Pool",
    "AsyncPool",
    "Provider",
    "Model",
    "Reply",
    "EmbedReply",
    "Metrics",
    "register_provider",
    "register_adapter",
    "FreeLLMPoolError",
    "NoProvidersConfigured",
    "AllProvidersExhausted",
    "ContextWindowExceeded",
    "__version__",
]
