"""freellmpool — pool free-tier LLM APIs behind one OpenAI-compatible endpoint.

Public API:

    from freellmpool import Pool

    pool = Pool.from_default_config()
    reply = pool.ask("Explain CAP theorem in one sentence.")
    print(reply.text)
"""

from .errors import AllProvidersExhausted, BuffetError, NoProvidersConfigured
from .models import EmbedReply, Model, Provider, Reply
from .router import Pool

__version__ = "0.9.2"

__all__ = [
    "Pool",
    "Provider",
    "Model",
    "Reply",
    "EmbedReply",
    "BuffetError",
    "NoProvidersConfigured",
    "AllProvidersExhausted",
    "__version__",
]
