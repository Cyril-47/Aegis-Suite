from enum import Enum
from typing import Callable, Optional, Set, Dict


class LifecycleState(str, Enum):
    BOOTING = "booting"
    SAFE_MODE = "safe_mode"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"


class ReasonCode(str, Enum):
    NEEDS_SETUP = "needs-setup"
    TOKEN_RECOVERY = "token-recovery"
    DB_RECOVERY = "db-recovery"
    INTENT_RECOVERY = "intent-recovery"


# Exact transition map from design.md
ALLOWED: Dict[LifecycleState, Set[LifecycleState]] = {
    LifecycleState.BOOTING: {
        LifecycleState.RUNNING,
        LifecycleState.SAFE_MODE,
        LifecycleState.SHUTTING_DOWN
    },
    LifecycleState.SAFE_MODE: {
        LifecycleState.RUNNING,
        LifecycleState.SHUTTING_DOWN
    },
    LifecycleState.RUNNING: {
        LifecycleState.SAFE_MODE,
        LifecycleState.SHUTTING_DOWN
    },
    LifecycleState.SHUTTING_DOWN: set()  # Terminal state
}


class LifecycleStateMachine:
    """Manages the application's lifecycle state machine, ensuring only allowed transitions occur."""

    def __init__(
        self,
        on_transition: Optional[Callable[[LifecycleState, Optional[ReasonCode]], None]] = None
    ) -> None:
        self._current_state: LifecycleState = LifecycleState.BOOTING
        self._reason: Optional[ReasonCode] = None
        self.on_transition: Optional[Callable[[LifecycleState, Optional[ReasonCode]], None]] = on_transition

    @property
    def current_state(self) -> LifecycleState:
        return self._current_state

    @property
    def reason(self) -> Optional[ReasonCode]:
        return self._reason

    def is_safe_mode(self) -> bool:
        return self._current_state == LifecycleState.SAFE_MODE

    def transition(self, to: LifecycleState, reason: Optional[ReasonCode] = None) -> None:
        """Transitions to the target state if allowed, invoking the transition hook."""
        # 1. Guard transition checks
        if to not in ALLOWED[self._current_state]:
            raise ValueError(f"Illegal state transition from {self._current_state} to {to}")

        # 2. Enforce reason code rules based on the target state
        if to == LifecycleState.SAFE_MODE:
            if not reason:
                raise ValueError("Entering SAFE_MODE requires a valid ReasonCode")
            if not isinstance(reason, ReasonCode):
                raise ValueError(f"Invalid ReasonCode type: {reason}")
            self._reason = reason
        else:
            if reason is not None:
                raise ValueError(f"State {to} cannot carry a ReasonCode")
            self._reason = None

        self._current_state = to

        # 3. Invoke the callback hook if registered
        if self.on_transition is not None:
            self.on_transition(self._current_state, self._reason)
