"""llmbuffet — pool free-tier LLM APIs behind one OpenAI-compatible endpoint.

Public API:

    from llmbuffet import Buffet

    buffet = Buffet.from_default_config()
    reply = buffet.ask("Explain CAP theorem in one sentence.")
    print(reply.text)
"""

from .errors import AllProvidersExhausted, BuffetError, NoProvidersConfigured
from .models import Model, Provider, Reply
from .router import Buffet

__version__ = "0.2.0"

__all__ = [
    "Buffet",
    "Provider",
    "Model",
    "Reply",
    "BuffetError",
    "NoProvidersConfigured",
    "AllProvidersExhausted",
    "__version__",
]
