import subprocess
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.RunScriptAction import RunScriptAction


class QuitAllAppsExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


def get_open_apps():
    """Return a list of unique app process names that have open windows"""
    result = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True)
    pids = {line.split()[2] for line in result.stdout.splitlines() if line.strip()}
    apps = set()
    for pid in pids:
        try:
            cmd = subprocess.check_output(
                ["ps", "-p", pid, "-o", "comm="], text=True
            ).strip()
            apps.add(cmd)
        except subprocess.CalledProcessError:
            continue
    # Exclude essentials
    blacklist = {"ulauncher", "gnome-shell", "gnome-terminal", "x-terminal-emulator"}
    return [a for a in apps if a not in blacklist]


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        open_apps = get_open_apps()
        if not open_apps:
            return RenderResultListAction(
                [
                    ExtensionResultItem(
                        name="No GUI apps detected",
                        description="All clean 👌",
                        icon="images/icon.png",
                    )
                ]
            )

        quit_script = " && ".join([f"pkill -f {app}" for app in open_apps])
        return RenderResultListAction(
            [
                ExtensionResultItem(
                    icon="images/icon.png",
                    name=f"Quit {len(open_apps)} open apps",
                    description=", ".join(open_apps),
                    on_enter=RunScriptAction(quit_script, None),
                )
            ]
        )


if __name__ == "__main__":
    QuitAllAppsExtension().run()
