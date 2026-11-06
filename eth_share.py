#!/usr/bin/env python3
"""
Ethernet Share - a tiny desktop app for the Raspberry Pi.

Click START and the Pi's Ethernet port starts handing out IP addresses
(192.168.2.x) and sharing the Pi's internet with whatever is plugged in.
The picture of the port lights up:

  left light  (LINK)   red = no cable / nothing plugged in, green = cable connected
  right light (SHARE)  red = not sharing,  amber = sharing, waiting for a device,
                       green = a device got an IP address

Click STOP to put the port back to normal.

Needs Raspberry Pi OS Bookworm or newer (NetworkManager) and python3-tk:
    sudo apt install -y python3-tk
Run:
    python3 eth_share.py
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

APP_NAME = "Ethernet Share"
IFACE = "eth0"
CON_NAME = "eth-share"
PI_ADDR = "192.168.2.1"
PREFIX = 24
POLL_SECONDS = 2

RED = "#e23b3b"
GREEN = "#2fd35a"
AMBER = "#f2b233"
OFF = "#4a1414"


# ---------------------------------------------------------------- system helpers
def run(cmd, timeout=30):
    """Run a command, return (ok, output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return False, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return False, "timed out"


def nmcli(*args, timeout=30):
    """Run nmcli; if NetworkManager says we're not allowed, ask for the password once via pkexec."""
    ok, out = run(["nmcli", *args], timeout=timeout)
    if not ok and ("Not authorized" in out or "Insufficient privileges" in out
                   or "not authorized" in out):
        if shutil.which("pkexec"):
            ok, out = run(["pkexec", "nmcli", *args], timeout=120)
    return ok, out


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def iface_exists():
    return os.path.isdir(f"/sys/class/net/{IFACE}")


def cable_connected():
    return read(f"/sys/class/net/{IFACE}/carrier") == "1"


def active_connection():
    ok, out = run(["nmcli", "-t", "-g", "GENERAL.CONNECTION", "device", "show", IFACE], timeout=5)
    return out.strip() if ok else ""


def profile_exists():
    ok, out = run(["nmcli", "-t", "-g", "NAME", "connection", "show"], timeout=5)
    return ok and CON_NAME in out.splitlines()


def eth_is_pi_internet():
    """True if the Pi's own default route currently goes out the Ethernet port."""
    ok, out = run(["ip", "-4", "route", "show", "default"], timeout=5)
    return ok and f"dev {IFACE}" in out


def connected_devices():
    """Devices that got an address from the port: [(ip, name, mac)]."""
    devices = {}
    leases = read(f"/var/lib/NetworkManager/dnsmasq-{IFACE}.leases")
    now = time.time()
    for line in leases.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            expiry, mac, ip, name = parts[:4]
            try:
                if int(expiry) and int(expiry) < now:
                    continue
            except ValueError:
                pass
            devices[ip] = (ip, "" if name == "*" else name, mac)
    # Only show leases for devices that are actually still there
    ok, out = run(["ip", "-4", "neigh", "show", "dev", IFACE], timeout=5)
    alive = set()
    if ok:
        for line in out.splitlines():
            p = line.split()
            if p and any(s in line for s in ("REACHABLE", "STALE", "DELAY", "PROBE")):
                alive.add(p[0])
                if p[0] not in devices and p[0].startswith(PI_ADDR.rsplit(".", 1)[0] + "."):
                    mac = p[p.index("lladdr") + 1] if "lladdr" in p else ""
                    devices[p[0]] = (p[0], "", mac)
    if alive:
        return [d for ip, d in devices.items() if ip in alive]
    return list(devices.values()) if cable_connected() else []


def start_sharing():
    nmcli("connection", "delete", CON_NAME)  # clean up an old copy, ignore errors
    ok, out = nmcli(
        "connection", "add", "type", "ethernet", "ifname", IFACE, "con-name", CON_NAME,
        "ipv4.method", "shared", "ipv4.addresses", f"{PI_ADDR}/{PREFIX}",
        "ipv6.method", "disabled",
        "connection.autoconnect", "yes", "connection.autoconnect-priority", "100",
    )
    if not ok:
        return False, out
    if cable_connected():
        ok, out = nmcli("connection", "up", CON_NAME, timeout=45)
        if not ok:
            return False, out
    # With no cable, NetworkManager brings it up by itself when one is plugged in.
    return True, ""


def stop_sharing():
    ok, out = nmcli("connection", "delete", CON_NAME)
    # Let the port go back to its normal wired profile
    run(["nmcli", "device", "connect", IFACE], timeout=20)
    return ok, out


# ---------------------------------------------------------------- desktop icon
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
<rect x="8" y="8" width="112" height="112" rx="18" fill="#2b2f36"/>
<path d="M28 40 h72 v52 h-18 v10 h-36 v-10 h-18 z" fill="#0d0f12"/>
<g fill="#d8b04a">
<rect x="36" y="42" width="5" height="16"/><rect x="45" y="42" width="5" height="16"/>
<rect x="54" y="42" width="5" height="16"/><rect x="63" y="42" width="5" height="16"/>
<rect x="72" y="42" width="5" height="16"/><rect x="81" y="42" width="5" height="16"/>
<rect x="90" y="42" width="5" height="16"/></g>
<rect x="18" y="16" width="22" height="12" rx="3" fill="#2fd35a"/>
<rect x="88" y="16" width="22" height="12" rx="3" fill="#2fd35a"/>
</svg>"""


def install_desktop_icon():
    script = os.path.abspath(__file__)
    icon_dir = os.path.expanduser("~/.local/share/icons")
    apps_dir = os.path.expanduser("~/.local/share/applications")
    desk_dir = os.path.expanduser("~/Desktop")
    os.makedirs(icon_dir, exist_ok=True)
    os.makedirs(apps_dir, exist_ok=True)
    icon = os.path.join(icon_dir, "eth-share.svg")
    with open(icon, "w") as f:
        f.write(ICON_SVG)
    entry = (
        "[Desktop Entry]\nType=Application\n"
        f"Name={APP_NAME}\nComment=Share the Pi's internet out the Ethernet port\n"
        f"Exec=python3 \"{script}\"\nIcon={icon}\nTerminal=false\n"
        "Categories=Network;\n"
    )
    paths = [os.path.join(apps_dir, "eth-share.desktop")]
    if os.path.isdir(desk_dir):
        paths.append(os.path.join(desk_dir, "eth-share.desktop"))
    for p in paths:
        with open(p, "w") as f:
            f.write(entry)
        os.chmod(p, 0o755)
        if shutil.which("gio"):
            run(["gio", "set", p, "metadata::trusted", "true"], timeout=5)
    return paths


# ---------------------------------------------------------------- GUI
class App:
    W, H = 360, 250

    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.resizable(False, False)
        root.configure(bg="#1d2025")
        self.busy = False
        self.blink = False
        self.state = {"exists": True, "cable": False, "sharing": False, "devices": [],
                      "eth_internet": False}

        self.canvas = tk.Canvas(root, width=self.W, height=self.H, bg="#1d2025",
                                highlightthickness=0)
        self.canvas.pack(padx=16, pady=(16, 6))
        self.draw_port()

        self.status = tk.Label(root, text="Checking...", fg="white", bg="#1d2025",
                               font=("DejaVu Sans", 13, "bold"))
        self.status.pack()
        self.detail = tk.Label(root, text="", fg="#b9c0ca", bg="#1d2025",
                               font=("DejaVu Sans Mono", 11), justify="center")
        self.detail.pack(pady=(4, 10))

        self.button = tk.Button(root, text="START", width=14, height=2,
                                font=("DejaVu Sans", 14, "bold"), fg="white",
                                bg="#2e9d4f", activebackground="#37b85d",
                                activeforeground="white", relief="flat",
                                command=self.toggle)
        self.button.pack(pady=(0, 10))

        small = tk.Frame(root, bg="#1d2025")
        small.pack(pady=(0, 12))
        tk.Button(small, text="Add desktop icon", relief="flat", bg="#343a43",
                  fg="white", activebackground="#444b55", activeforeground="white",
                  command=self.add_icon).pack(side="left", padx=4)

        self.poll()
        self.tick()

    # --- drawing an RJ45 jack
    def draw_port(self):
        c = self.canvas
        cx = self.W // 2
        # metal housing
        c.create_rectangle(cx - 150, 20, cx + 150, 230, fill="#c9ccd1", outline="#8d9198", width=3)
        c.create_rectangle(cx - 140, 30, cx + 140, 220, fill="#b3b7bd", outline="")
        # the opening (with the clip notch at the bottom)
        pts = [cx - 110, 70, cx + 110, 70, cx + 110, 180, cx + 45, 180,
               cx + 45, 205, cx - 45, 205, cx - 45, 180, cx - 110, 180]
        c.create_polygon(pts, fill="#0d0f12", outline="#2a2d33", width=2)
        # 8 gold contacts
        for i in range(8):
            x = cx - 84 + i * 24
            c.create_rectangle(x - 5, 76, x + 5, 118, fill="#d8b04a", outline="#a3812c")
        # LEDs
        self.led_link = c.create_rectangle(cx - 140, 34, cx - 92, 58, fill=OFF, outline="#222")
        self.led_share = c.create_rectangle(cx + 92, 34, cx + 140, 58, fill=OFF, outline="#222")
        self.glow_link = c.create_oval(cx - 150, 26, cx - 82, 66, outline="", fill="")
        self.glow_share = c.create_oval(cx + 82, 26, cx + 150, 66, outline="", fill="")
        c.tag_lower(self.glow_link)
        c.tag_lower(self.glow_share)
        c.create_text(cx - 116, 12, text="LINK", fill="#b9c0ca", font=("DejaVu Sans", 9, "bold"))
        c.create_text(cx + 116, 12, text="SHARE", fill="#b9c0ca", font=("DejaVu Sans", 9, "bold"))
        c.create_text(cx, 150, text=IFACE, fill="#5c636e", font=("DejaVu Sans", 16, "bold"))

    def set_led(self, led, color):
        self.canvas.itemconfigure(led, fill=color)

    # --- refresh the picture and text from self.state
    def render(self):
        s = self.state
        link_col = GREEN if s["cable"] else RED
        if not s["sharing"]:
            share_col = RED
        elif s["devices"]:
            share_col = GREEN
        else:
            share_col = AMBER if self.blink else OFF
        self.set_led(self.led_link, link_col)
        self.set_led(self.led_share, share_col)

        if not s["exists"]:
            self.status.config(text=f"No {IFACE} port found", fg=RED)
            self.detail.config(text="")
        elif self.busy:
            pass
        elif not s["sharing"]:
            self.status.config(text="Port is OFF", fg=RED)
            self.detail.config(text="Click START to share the Pi's internet\nthrough the Ethernet port.")
        elif not s["cable"]:
            self.status.config(text="Ready - plug in a cable", fg=AMBER)
            self.detail.config(text=f"Pi port address: {PI_ADDR}")
        elif not s["devices"]:
            self.status.config(text="Waiting for the device...", fg=AMBER)
            self.detail.config(text=f"Pi port address: {PI_ADDR}")
        else:
            self.status.config(text="Connected", fg=GREEN)
            lines = []
            for ip, name, mac in s["devices"][:4]:
                lines.append(f"Device IP: {ip}" + (f"  ({name})" if name else ""))
            lines.append(f"Gateway (Pi): {PI_ADDR}")
            self.detail.config(text="\n".join(lines))

        if not self.busy:
            if s["sharing"]:
                self.button.config(text="STOP", bg="#c0392b", activebackground="#d64a3b",
                                   state="normal")
            else:
                self.button.config(text="START", bg="#2e9d4f", activebackground="#37b85d",
                                   state="normal" if s["exists"] else "disabled")

    # --- background status check
    def poll(self):
        def work():
            st = {
                "exists": iface_exists(),
                "cable": cable_connected(),
                "sharing": profile_exists(),
                "eth_internet": eth_is_pi_internet(),
            }
            st["devices"] = connected_devices() if st["sharing"] and st["cable"] else []
            self.root.after(0, self._update_state, st)
        threading.Thread(target=work, daemon=True).start()
        self.root.after(POLL_SECONDS * 1000, self.poll)

    def _update_state(self, st):
        self.state.update(st)
        self.render()

    def tick(self):
        self.blink = not self.blink
        self.render()
        self.root.after(600, self.tick)

    # --- buttons
    def toggle(self):
        if self.busy:
            return
        if self.state["sharing"]:
            self.do_in_background(stop_sharing, "Stopping...", "Couldn't stop sharing")
        else:
            if self.state["eth_internet"] and not messagebox.askyesno(
                    APP_NAME,
                    "The Pi is getting its own internet through this Ethernet port right now.\n\n"
                    "Sharing will take that connection away. Continue?"):
                return
            self.do_in_background(start_sharing, "Starting...", "Couldn't start sharing")

    def do_in_background(self, fn, busy_text, fail_text):
        self.busy = True
        self.status.config(text=busy_text, fg=AMBER)
        self.detail.config(text="You may be asked for your password.")
        self.button.config(state="disabled")

        def work():
            ok, out = fn()
            self.root.after(0, self._done, ok, out, fail_text)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, ok, out, fail_text):
        self.busy = False
        if not ok:
            messagebox.showerror(APP_NAME, f"{fail_text}.\n\n{out[-600:]}")
        self.poll_once()

    def poll_once(self):
        def work():
            st = {"exists": iface_exists(), "cable": cable_connected(),
                  "sharing": profile_exists(), "eth_internet": eth_is_pi_internet()}
            st["devices"] = connected_devices() if st["sharing"] and st["cable"] else []
            self.root.after(0, self._update_state, st)
        threading.Thread(target=work, daemon=True).start()

    def add_icon(self):
        try:
            paths = install_desktop_icon()
            messagebox.showinfo(APP_NAME, "Icon added:\n" + "\n".join(paths))
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Couldn't add the icon:\n{e}")


def main():
    if not shutil.which("nmcli"):
        print("This app needs NetworkManager (nmcli). Raspberry Pi OS Bookworm or newer has it.")
        sys.exit(1)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
