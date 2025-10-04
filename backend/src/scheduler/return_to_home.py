from __future__ import annotations


class ReturnToHome:
    """Simple return-to-home action builder (FR-041).

    Produces a navigation action descriptor; wiring to the waypoint
    controller happens in integration tasks.
    """

    def make_action(self) -> dict:
        return {
            "type": "navigate",
            "target_waypoint_type": "home",
            "metadata": {},
        }


__all__ = ["ReturnToHome"]
