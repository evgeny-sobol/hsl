import argparse
import ctypes
import subprocess
import time
from datetime import datetime
from pathlib import Path

EXTS = {".hsl", ".hml", ".include"}

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32


def raise_console():
    """Pull the console window to the foreground. Windows blocks
    SetForegroundWindow from background processes, so briefly attach to the
    current foreground thread's input queue to lift the restriction."""
    hwnd = k32.GetConsoleWindow()
    if not hwnd:
        return
    if u32.IsIconic(hwnd):
        u32.ShowWindow(hwnd, 9)  # SW_RESTORE

    fg = u32.GetForegroundWindow()
    if fg == hwnd:
        return

    cur_tid = k32.GetCurrentThreadId()
    fg_tid = u32.GetWindowThreadProcessId(fg, None)

    attached = fg_tid and fg_tid != cur_tid and u32.AttachThreadInput(cur_tid, fg_tid, True)
    try:
        u32.BringWindowToTop(hwnd)
        if not u32.SetForegroundWindow(hwnd):
            u32.FlashWindow(hwnd, True)  # fallback: blink in the taskbar
    finally:
        if attached:
            u32.AttachThreadInput(cur_tid, fg_tid, False)


def alert(code):
    if code == 0:
        return
    print(f"\a\033[91m*** COMPILATION FAILED (exit {code}) ***\033[0m")
    raise_console()


def snapshot(watch_dir):
    return {p: p.stat().st_mtime for p in watch_dir.rglob("*") if p.suffix in EXTS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target_dir", nargs="?", default=".")
    ap.add_argument("vanilla_root", nargs="?")
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument("-f", "--force", action="store_true")
    args = ap.parse_args()

    watch_dir = Path(args.target_dir)

    cmd = ["python", "compiler.py", args.target_dir]
    if args.vanilla_root:
        cmd.append(args.vanilla_root)
    if args.force:
        cmd.append("--force")

    print(f"Watching {watch_dir.resolve()}")

    prev = snapshot(watch_dir)
    try:
        while True:
            time.sleep(args.interval)
            cur = snapshot(watch_dir)
            if cur != prev:
                print(f"\n{datetime.now():%H:%M:%S %d.%m.%Y}")
                alert(subprocess.run(cmd).returncode)
                # re-snapshot after the build so generated .txt files don't
                # retrigger on the next tick
                prev = snapshot(watch_dir)
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
