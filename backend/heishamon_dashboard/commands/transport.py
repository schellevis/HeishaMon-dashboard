"""The publish interface the command service needs, and the wrapper that routes plans onto it."""
from typing import Protocol

from heishamon_dashboard.commands.planner import Plan
from heishamon_dashboard.mqtt import PublishError

__all__ = ["Publisher", "PublishError", "Transport"]


class Publisher(Protocol):
    async def publish_command(self, name: str, payload: str) -> None: ...
    async def publish_input(self, name: str, payload: str) -> None: ...
    async def publish_retained_exception(self, name: str, payload: str) -> None: ...


class Transport:
    """Routes a plan to the right publish call. Broker failures surface as `PublishError`."""

    def __init__(self, publisher: Publisher) -> None:
        self._publisher = publisher

    async def publish(self, plan: Plan, payload: str) -> None:
        if plan.kind == "input":
            if plan.cls == "retained_exception":
                await self._publisher.publish_retained_exception(plan.name, payload)
            else:
                await self._publisher.publish_input(plan.name, payload)
        else:
            await self._publisher.publish_command(plan.name, payload)
