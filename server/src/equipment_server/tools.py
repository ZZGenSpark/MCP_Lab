"""Plain tool functions. MCP registration lives in server.py."""

from __future__ import annotations

from typing import Any

from equipment_server.loaders import PolicyData, load_policies
from equipment_server.validation import policy_roles, validate_role


def get_policy_limits(
    role: object, *, policies: PolicyData | None = None
) -> dict[str, Any]:
    """Return one role's item limits and the items that role may request.

    The role is trimmed and lowercased. An unknown or empty role returns a
    structured tool error and does not read any other policy fields.
    """
    policies = load_policies() if policies is None else policies
    normalized = validate_role(role, policy_roles(policies))
    if isinstance(normalized, dict):
        return normalized
    limits = [
        {
            "item": limit.item,
            "max_quantity": limit.max_quantity,
            "refresh_years": limit.refresh_years,
        }
        for limit in policies.limits
        if limit.role == normalized
    ]
    return {
        "ok": True,
        "role": normalized,
        "eligible_items": [row["item"] for row in limits if row["max_quantity"] > 0],
        "limits": limits,
    }
