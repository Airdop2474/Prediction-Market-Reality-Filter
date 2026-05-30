from typing import Any


class BaseAgent:
    name = "base_agent"

    async def analyze(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError
