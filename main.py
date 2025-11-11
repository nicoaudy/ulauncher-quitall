import subprocess
import shutil
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction


class QuitAllAppsExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


def check_dependencies():
    """Check if wmctrl is installed"""
    return shutil.which("wmctrl") is not None


def get_open_apps(exclude_list):
    """Return a list of unique app process names that have open windows"""
    if not check_dependencies():
        return None

    try:
        result = subprocess.run(
            ["wmctrl", "-lp"], capture_output=True, text=True, check=True, timeout=5
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []

    pids = set()
    for line in result.stdout.splitlines():
        if line.strip():
            parts = line.split()
            if len(parts) >= 3:
                pids.add(parts[2])

    apps = set()
    for pid in pids:
        try:
            cmd = subprocess.check_output(
                ["ps", "-p", pid, "-o", "comm="], text=True, timeout=2
            ).strip()
            if cmd and cmd not in exclude_list:
                apps.add(cmd)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue

    return sorted(list(apps))


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        # Check if wmctrl is installed
        if not check_dependencies():
            install_cmd = "sudo apt install wmctrl"
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="⚠️ wmctrl not installed",
                        description="Click to copy installation command",
                        on_enter=CopyToClipboardAction(install_cmd),
                    ),
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="Installation command:",
                        description=install_cmd,
                        on_enter=CopyToClipboardAction(install_cmd),
                    ),
                ]
            )

        # Get excluded apps from preferences
        exclude_pref = extension.preferences.get("exclude_list", "")
        exclude_list = {app.strip() for app in exclude_pref.split(",") if app.strip()}

        # Add essential system processes that should never be killed
        exclude_list.update(
            {
                "ulauncher",
                "gnome-shell",
                "gnome-terminal",
                "x-terminal-emulator",
                "systemd",
                "dbus-daemon",
                "plasmashell",
                "kwin_x11",
                "xfwm4",
                "xfce4-panel",
            }
        )

        open_apps = get_open_apps(exclude_list)

        # Handle error case
        if open_apps is None:
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        icon="images/icon.png",
                        name="Error checking dependencies",
                        description="Please restart Ulauncher",
                    )
                ]
            )

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

        # Create a bash script to kill all apps
        # Use pkill -x for exact matching (safer than -f)
        kill_commands = []
        for app in open_apps:
            # Escape single quotes in app names
            safe_app = app.replace("'", "'\\''")
            kill_commands.append(f"pkill -x '{safe_app}' 2>/dev/null")

        # Join with ; and wrap in bash -c
        quit_script = f'bash -c "{"; ".join(kill_commands)}"'

        return RenderResultListAction(
            [
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=f"🚫 Quit {len(open_apps)} open app{'s' if len(open_apps) > 1 else ''}",
                    description=", ".join(open_apps[:8])
                    + ("..." if len(open_apps) > 8 else ""),
                    on_enter=RunScriptAction(quit_script),
                )
            ]
        )


if __name__ == "__main__":
    QuitAllAppsExtension().run()
