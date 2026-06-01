from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from aegis.core.state import LifecycleState, ReasonCode


@dataclass
class HealthRegistry:
    """In-memory registry tracking the cached status of each application subsystem."""
    web: str = "down"
    database: Dict[str, Any] = field(
        default_factory=lambda: {"reachable": False, "integrity_ok": False, "at_head": False}
    )
    bot: str = "disabled"
    intents: str = "unknown"
    safe_mode: Any = False
    lifecycle_state: str = "booting"
    checks: Dict[str, Any] = field(default_factory=dict)

    def record_state(self, state: LifecycleState, reason: Optional[ReasonCode] = None) -> None:
        """Update cached lifecycle state and safe mode status."""
        self.lifecycle_state = state.value
        if state == LifecycleState.SAFE_MODE:
            self.safe_mode = {
                "active": True,
                "reason": reason.value if reason else None
            }
        else:
            self.safe_mode = False

    def record_check(self, name: str, verdict: str) -> None:
        """Cache a startup check verdict."""
        self.checks[name] = verdict

    def record_fatal(self, exc: Exception) -> None:
        """Record sanitized exception metadata to prevent sensitive traceback leakage."""
        self.checks["fatal_error"] = {
            "type": exc.__class__.__name__,
            "recorded": True
        }

    def payload(self) -> Dict[str, Any]:
        """Assembles and returns the health payload. Conforms strictly to cache-only constraints (no I/O)."""
        return {
            "lifecycle_state": self.lifecycle_state,
            "web": self.web,
            "database": self.database,
            "bot": self.bot,
            "intents": self.intents,
            "safe_mode": self.safe_mode,
            "checks": self.checks,
        }
