"""freellmpool — pool free-tier LLM APIs behind one OpenAI-compatible endpoint.

Public API:

    from freellmpool import Pool

    pool = Pool.from_default_config()
    reply = pool.ask("Explain CAP theorem in one sentence.")
    print(reply.text)
"""

from .errors import AllProvidersExhausted, BuffetError, NoProvidersConfigured
from .models import Model, Provider, Reply
from .router import Pool

__version__ = "0.3.0"

__all__ = [
    "Pool",
    "Provider",
    "Model",
    "Reply",
    "BuffetError",
    "NoProvidersConfigured",
    "AllProvidersExhausted",
    "__version__",
]
