import subprocess
import shutil
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction


class QuitAllAppsExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())


def check_dependencies():
    """Check if wmctrl is installed"""
    return shutil.which("wmctrl") is not None


def get_window_pids():
    """Get PIDs of windows using xdotool (more reliable than wmctrl -lp)"""
    try:
        # Get all visible window IDs
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", ""],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return set()

        window_ids = [wid.strip() for wid in result.stdout.split() if wid.strip()]
        pids = set()

        for wid in window_ids:
            try:
                pid_result = subprocess.run(
                    ["xdotool", "getwindowpid", wid],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if pid_result.returncode == 0:
                    pid = pid_result.stdout.strip()
                    if pid.isdigit():
                        pids.add(pid)
            except Exception:
                continue

        return pids
    except Exception:
        return set()


def get_open_apps(exclude_list):
    """Return a list of unique app process names that have open windows"""
    # Try xdotool first (more reliable)
    pids = get_window_pids()

    # Fallback to wmctrl if xdotool fails
    if not pids:
        try:
            # Use wmctrl -lx to get class names directly
            result = subprocess.run(
                ["wmctrl", "-lx"], capture_output=True, text=True, timeout=5
            )

            # Extract class names (format: window_id desktop class hostname title)
            classes = set()
            for line in result.stdout.splitlines():
                if line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 3:
                        # Class is in format: instance.class
                        class_full = parts[2]
                        class_name = class_full.split(".")[0].lower()
                        if class_name and class_name not in exclude_list:
                            classes.add(class_name)

            return sorted(list(classes))

        except Exception:
            return []

    # Get process names from PIDs
    apps = set()
    for pid in pids:
        try:
            cmd = subprocess.check_output(
                ["ps", "-p", pid, "-o", "comm="], text=True, timeout=2
            ).strip()
            if cmd and cmd not in exclude_list:
                apps.add(cmd)
        except Exception:
            continue

    return sorted(list(apps))


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        # Check if required tools are installed
        has_wmctrl = shutil.which("wmctrl") is not None
        has_xdotool = shutil.which("xdotool") is not None

        if not has_wmctrl and not has_xdotool:
            install_cmd = "sudo apt install wmctrl xdotool"
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="⚠️ Missing dependencies",
                        description="Click to copy: sudo apt install wmctrl xdotool",
                        on_enter=CopyToClipboardAction(install_cmd),
                    ),
                ]
            )
        elif not has_xdotool:
            install_cmd = "sudo apt install xdotool"
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="⚠️ xdotool recommended",
                        description="Click to copy: sudo apt install xdotool (for better detection)",
                        on_enter=CopyToClipboardAction(install_cmd),
                    ),
                ]
            )

        # Get excluded apps from preferences
        exclude_pref = extension.preferences.get("exclude_list", "")
        exclude_list = {
            app.strip().lower() for app in exclude_pref.split(",") if app.strip()
        }

        # Add essential system processes that should never be killed
        exclude_list.update(
            {
                "ulauncher",
                "gnome-shell",
                "gnome-terminal",
                "konsole",
                "terminator",
                "x-terminal-emulator",
                "systemd",
                "dbus-daemon",
                "dbus-broker",
                "plasmashell",
                "kwin_x11",
                "kwin_wayland",
                "xfwm4",
                "xfce4-panel",
                "xorg",
                "xwayland",
                "nautilus",
                "dolphin",
                "thunar",
                "pcmanfm",
                "kworker",
                "rcu_gp",
                "kthreadd",
                "migration",  # Kernel threads
            }
        )

        open_apps = get_open_apps(exclude_list)

        if not open_apps:
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="No GUI apps to quit",
                        description="All apps are already closed 👌",
                    )
                ]
            )

        # Return action that will trigger the quit
        return RenderResultListAction(
            [
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=f"🚫 Quit {len(open_apps)} open app{'s' if len(open_apps) > 1 else ''}",
                    description=", ".join(open_apps[:8])
                    + ("..." if len(open_apps) > 8 else ""),
                    on_enter=ExtensionCustomAction(
                        {"action": "quit_apps", "apps": open_apps}
                    ),
                )
            ]
        )


class ItemEnterEventListener(EventListener):
    """Handles the actual quitting of apps when user presses Enter"""

    def on_event(self, event, extension):
        data = event.get_data()

        if data.get("action") != "quit_apps":
            return

        apps = data.get("apps", [])

        if not apps:
            return HideWindowAction()

        # Quit each app using multiple methods
        for app in apps:
            # Method 1: Try pkill with exact match
            try:
                subprocess.run(
                    ["pkill", "-x", app],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            except Exception:
                pass

            # Method 2: Try pkill with case-insensitive partial match
            try:
                subprocess.run(
                    ["pkill", "-i", app],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            except Exception:
                pass

            # Method 3: Try killall
            try:
                subprocess.run(
                    ["killall", "-q", app],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            except Exception:
                pass

            # Method 4: For apps with capital letters (like Slack, Chrome)
            try:
                subprocess.run(
                    ["killall", "-q", app.capitalize()],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                )
            except Exception:
                pass

        return HideWindowAction()


if __name__ == "__main__":
    QuitAllAppsExtension().run()
