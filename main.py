import subprocess
import shutil
import time
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


def get_window_pids():
    """Get PIDs of visible windows using xdotool"""
    try:
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

        return pids
    except Exception:
        return set()


def get_open_apps(exclude_list):
    """Return a list of app process names with open windows"""
    pids = get_window_pids()

    if not pids:
        try:
            result = subprocess.run(
                ["wmctrl", "-lx"], capture_output=True, text=True, timeout=5
            )
            classes = set()
            for line in result.stdout.splitlines():
                if line.strip():
                    parts = line.split(None, 4)
                    if len(parts) >= 3:
                        class_full = parts[2]
                        class_name = class_full.split(".")[0].lower()
                        if class_name and class_name not in exclude_list:
                            classes.add(class_name)
            return sorted(list(classes))
        except Exception:
            return []

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


def force_kill(app):
    """Try graceful kill first, then force if still alive"""
    try:
        # Try normal TERM signal
        subprocess.run(
            ["pkill", "-TERM", "-i", app], timeout=2, stderr=subprocess.DEVNULL
        )
        time.sleep(0.5)
        # Check if still alive
        check = subprocess.run(["pgrep", "-i", app], capture_output=True, text=True)
        if check.returncode == 0:
            # Force kill remaining processes
            subprocess.run(
                ["pkill", "-9", "-i", app], timeout=2, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
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

        exclude_pref = extension.preferences.get("exclude_list", "")
        exclude_list = {
            app.strip().lower() for app in exclude_pref.split(",") if app.strip()
        }

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
                "migration",
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
    """Handles quitting apps when user presses Enter"""

    def on_event(self, event, extension):
        data = event.get_data()
        if data.get("action") != "quit_apps":
            return

        apps = data.get("apps", [])
        if not apps:
            return HideWindowAction()

        for app in apps:
            force_kill(app)

        return HideWindowAction()


if __name__ == "__main__":
    QuitAllAppsExtension().run()
