"""Replace this factory with a System 2 coordinator when it is implemented."""

from tronclass.config import Settings
from tronclass.contracts import AssistantBackend
from tronclass.system1 import System1Assistant


def create_backend(settings: Settings, name: str = "system1") -> AssistantBackend:
    if name == "system1":
        return System1Assistant(settings)
    raise ValueError(f"尚未實作此 backend：{name}")
