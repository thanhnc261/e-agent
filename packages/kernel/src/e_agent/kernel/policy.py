"""Trusted platform policy (not replaceable by tenant plugins)."""

from __future__ import annotations

from e_agent.contracts.capability import CapabilityDescriptor, EffectKind
from e_agent.contracts.context import TaskContext
from e_agent.sdk.ports import PolicyDecision

REQUESTER_ROLE = "requester"
APPROVER_ROLE = "approver"


class DefaultPolicy:
    """MVP policy: requesters may read in-scope connections; every write needs approval."""

    version = "policy-mvp-1"

    def evaluate(
        self, ctx: TaskContext, descriptor: CapabilityDescriptor, connection_id: str
    ) -> PolicyDecision:
        reasons: list[str] = []
        if REQUESTER_ROLE not in ctx.principal.roles:
            reasons.append("principal lacks requester role")
        if connection_id not in ctx.resource_scope:
            reasons.append("connection outside authorized scope")
        if reasons:
            return PolicyDecision(False, False, self.version, tuple(reasons))
        return PolicyDecision(
            permitted=True,
            requires_approval=descriptor.effect is EffectKind.WRITE,
            policy_version=self.version,
        )
