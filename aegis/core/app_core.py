import os
import logging
import asyncio
import time
from typing import Optional, List, Any
from aegis.core.paths import Paths
from aegis.core.health import HealthRegistry
from aegis.core.state import LifecycleStateMachine, LifecycleState, ReasonCode

logger = logging.getLogger("aegis.core.app_core")

_active_cores = []


class AppCore:
    """The central orchestrator owning the asyncio event loop lifecycle and subsystems."""

    def __init__(self, paths: Optional[Paths] = None) -> None:
        self.paths = paths if paths is not None else Paths()
        
        # Set config path in unified ConfigManager
        try:
            from aegis.core.config_manager import get_config_manager
            get_config_manager().set_config_path(str(self.paths.config_file))
        except Exception as e:
            logger.warning(f"Failed to set ConfigManager path in AppCore: {e}")

        self._start_time = time.time()
        self.health = HealthRegistry()
        # Initialize LifecycleStateMachine with a transition callback hook to update health
        self.state = LifecycleStateMachine(on_transition=self._on_state_transition)
        
        self.config: Optional[Any] = None
        self.db: Optional[Any] = None
        self.analytics_db: Optional[Any] = None
        self.analytics_engine: Optional[Any] = None
        self.analytics_aggregator: Optional[Any] = None
        
        self._asgi_task: Optional[asyncio.Task] = None
        self._bot_task: Optional[asyncio.Task] = None
        self._uvicorn_server: Optional[Any] = None
        self.web_port: Optional[int] = None
        
        self._shutdown_requests: int = 0
        self._shutting_down: bool = False
        self._shutdown_event = asyncio.Event()
        
        # Shutdown event logger to verify exact teardown sequence ordering
        self.teardown_log: List[str] = []

        _active_cores.append(self)

    def _on_state_transition(self, state: LifecycleState, reason: Optional[ReasonCode]) -> None:
        """Invoked on every state transition to update the HealthRegistry."""
        self.health.record_state(state, reason)
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop is not None:
            if state == LifecycleState.SAFE_MODE:
                self._start_asgi_server_if_needed()
                self._cancel_bot_task_if_active()
            elif state == LifecycleState.RUNNING:
                self._start_asgi_server_if_needed()
                self._start_bot_task_if_needed()
                # Start analytics engine and aggregator
                if self.analytics_engine is not None:
                    try:
                        self.analytics_engine.start(loop)
                    except Exception as e:
                        logger.warning(f"Analytics engine start failed: {e}")
                if self.analytics_aggregator is not None:
                    try:
                        self.analytics_aggregator.start(loop)
                    except Exception as e:
                        logger.warning(f"Analytics aggregator start failed: {e}")

    def _start_asgi_server_if_needed(self) -> None:
        if self._asgi_task is None or self._asgi_task.done():
            from aegis.web.app import build_app
            from aegis.web.server import serve
            app = build_app(self)
            self._asgi_task = asyncio.create_task(serve(self, app))

    def _cancel_bot_task_if_active(self) -> None:
        if self._bot_task is not None and not self._bot_task.done():
            self._bot_task.cancel()
            self._bot_task = None
            self.health.bot = "disabled"

    def _start_bot_task_if_needed(self) -> None:
        if self._bot_task is None or self._bot_task.done():
            from aegis.core.utils import get_bot_token
            config_dict = self.config.as_dict() if self.config else None
            token = get_bot_token(config_dict)
            if not token:
                logger.error("Cannot start bot task: Discord token is missing.")
                self.health.bot = "disabled"
                return
            
            from aegis.bot.runner import start_bot_task
            self._bot_task = asyncio.create_task(start_bot_task(self, token))
            self._bot_task.add_done_callback(self._on_bot_task_done)
            self.health.bot = "connected_ready"

    def _on_bot_task_done(self, task: asyncio.Task) -> None:
        """Callback when the bot task terminates unexpectedly."""
        if self.state.current_state == LifecycleState.RUNNING:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception("Bot task exited with exception")
                self.health.record_fatal(e)
            
            # Initiate safe mode transition
            asyncio.create_task(self.enter_safe_mode(ReasonCode.TOKEN_RECOVERY))

    async def _bot_task_placeholder(self) -> None:
        """A placeholder implementation for the bot task in Phase 4."""
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.health.bot = "disabled"
            raise

    async def enter_safe_mode(self, reason: ReasonCode) -> None:
        """Idempotently transitions the application into SAFE_MODE."""
        self.state.transition(LifecycleState.SAFE_MODE, reason)

    async def promote_to_running(self) -> None:
        """Transitions the application into RUNNING."""
        self.state.transition(LifecycleState.RUNNING)

    async def request_shutdown(self) -> None:
        """Idempotent, timeout-bounded teardown sequence."""
        self._shutdown_requests += 1

        # Double shutdown signal triggers immediate hard exit
        if self._shutdown_requests >= 2:
            os._exit(0)

        if self._shutting_down:
            return

        self._shutting_down = True

        # 1. Transition state machine to SHUTTING_DOWN first
        self.state.transition(LifecycleState.SHUTTING_DOWN)
        self.teardown_log.append("state")

        current_t = asyncio.current_task()

        # 2. Cancel bot task
        if self._bot_task is not None and not self._bot_task.done():
            self.teardown_log.append("bot_cancel")
            if current_t != self._bot_task:
                self._bot_task.cancel()
                
                # 3. Await bot.close() connection close within 10.0s
                try:
                    await asyncio.wait_for(self._bot_task, timeout=10.0)
                except (asyncio.CancelledError, Exception):
                    pass
        self.teardown_log.append("bot_close")

        # 4. Stop ASGI task within 10.0s
        if self._asgi_task is not None and not self._asgi_task.done():
            self.teardown_log.append("asgi_stop")
            if self._uvicorn_server is not None:
                # Set should_exit to stop programmatic uvicorn
                self._uvicorn_server.should_exit = True
            
            if current_t != self._asgi_task:
                try:
                    await asyncio.wait_for(self._asgi_task, timeout=10.0)
                except (asyncio.CancelledError, Exception):
                    pass

        # 5. Dispose database engine
        if self.db is not None:
            self.teardown_log.append("db_dispose")
            try:
                if hasattr(self.db, "dispose"):
                    self.db.dispose()
            except Exception as e:
                logger.error(f"Error disposing database: {e}")

        # 5b. Dispose analytics database engine
        if self.analytics_db is not None:
            self.teardown_log.append("analytics_db_dispose")
            try:
                if hasattr(self.analytics_db, "dispose"):
                    self.analytics_db.dispose()
            except Exception as e:
                logger.error(f"Error disposing analytics database: {e}")

        # 5c. Stop analytics aggregator
        if self.analytics_aggregator is not None:
            self.analytics_aggregator.stop()

        # 6. Flush logging
        self.teardown_log.append("logging_shutdown")
        logging.shutdown()

        # 7. Signal completion and wake up run()
        self._shutdown_event.set()

    async def _perform_startup(self) -> None:
        """Runs the 7 startup checks using run_startup_checks."""
        from aegis.core.lifecycle import run_startup_checks
        verdict, reason = await run_startup_checks(self)
        await self._enter_post_startup_state(verdict, reason)

    async def _enter_post_startup_state(self, verdict: str, reason: Optional[ReasonCode]) -> None:
        if verdict == "FATAL-to-app":
            await self.request_shutdown()
            return

        if verdict == "FATAL-to-bot":
            await self.enter_safe_mode(reason)
        else:
            await self.promote_to_running()

        # Wait for the ASGI server task to start and assign web_port
        for _ in range(20):
            if self.web_port is not None:
                break
            await asyncio.sleep(0.1)

        if self.web_port is not None:
            import webbrowser
            try:
                webbrowser.open(f"http://127.0.0.1:{self.web_port}")
            except Exception as e:
                logger.warning(f"Failed to open browser automatically: {e}")
        else:
            logger.error("Web server did not start in time. Browser auto-open bypassed.")


    async def run(self) -> int:
        """Top-level async entry boundary. Returns exit code 0."""
        try:
            await self._perform_startup()
        except Exception as exc:
            # All logged tracebacks go through the Phase 1 RedactionFilter automatically (C4)
            logger.exception("Fatal exception during startup")
            self.health.record_fatal(exc)
            
            # Transition to SAFE_MODE with appropriate ReasonCode (defaulting to db-recovery)
            self.state.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)

        # Keep process alive while in safe mode or running state
        if self.state.current_state in (LifecycleState.SAFE_MODE, LifecycleState.RUNNING):
            await self._shutdown_event.wait()

        return 0
