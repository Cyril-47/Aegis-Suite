import os
import sys
import logging
from PIL import Image
import pystray
from pystray import MenuItem as item

logger = logging.getLogger("aegis.tray")


class SystemTrayManager:
    """Manages the Windows System Tray Icon (Notification Area) for Aegis Suite."""

    def __init__(self, root_dir: str, on_open_callback=None, on_exit_callback=None):
        self.root_dir = root_dir
        self.on_open_callback = on_open_callback
        self.on_exit_callback = on_exit_callback
        self.icon = None
        self._has_notified_close = False
        self._setup_icon()

    def _get_icon_image(self):
        """Loads logo image for system tray."""
        icon_paths = [
            os.path.join(self.root_dir, "aegis", "core", "tray_icon.png"),
            os.path.join(self.root_dir, "static", "bot_logo.png"),
            os.path.join(self.root_dir, "logo.ico"),
            os.path.join(self.root_dir, "bot_logo.png"),
            os.path.join(self.root_dir, "static", "favicon.ico"),
        ]
        for path in icon_paths:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    return img
                except Exception as e:
                    logger.warning(f"Could not load tray icon image from {path}: {e}")

        # Fallback 64x64 colored icon if no image file exists
        img = Image.new("RGBA", (64, 64), (88, 101, 242, 255))
        return img

    def _setup_icon(self):
        """Initializes PyStray Icon and context menu."""
        image = self._get_icon_image()
        
        menu = (
            item("Open Aegis Suite", self._on_open_clicked, default=True),
            item("Bot Status: Active", None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Exit Aegis Suite Completely", self._on_exit_clicked),
        )

        self.icon = pystray.Icon(
            name="AegisSuite",
            icon=image,
            title="Aegis Suite — Running in Background",
            menu=menu
        )

    def _on_open_clicked(self, icon, item):
        """Callback when user clicks 'Open Aegis Suite' or double-clicks tray icon."""
        if self.on_open_callback:
            self.on_open_callback()

    def _on_exit_clicked(self, icon, item):
        """Callback when user clicks 'Exit Aegis Suite Completely'."""
        logger.info("User requested full exit from system tray icon menu.")
        if self.icon:
            self.icon.stop()
        if self.on_exit_callback:
            self.on_exit_callback()

    def notify_background_running(self):
        """Displays balloon notification warning user that the app remains online in background."""
        if not self._has_notified_close and self.icon:
            self._has_notified_close = True
            try:
                self.icon.notify(
                    message="Aegis Suite is still running in the background to keep your Discord bot online.\nRight-click this tray icon to exit completely.",
                    title="Aegis Suite — Running in Background"
                )
            except Exception as e:
                logger.warning(f"Could not display tray balloon notification: {e}")

    def run_detached(self):
        """Runs PyStray icon loop in non-blocking detached thread."""
        try:
            self.icon.run_detached()
            logger.info("System Tray Icon started in background.")
        except Exception as e:
            logger.error(f"Failed to start System Tray Icon: {e}")

    def stop(self):
        """Stops tray icon."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
