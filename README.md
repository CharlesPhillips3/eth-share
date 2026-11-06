# Ethernet Share

A tiny desktop app for the Raspberry Pi. Click **START** and the Pi's Ethernet port hands out IP addresses and shares the Pi's internet with whatever is plugged in. Click **STOP** to put the port back to normal.

![Ethernet Share: off (left) and connected with a device at 192.168.2.23 (right)](screenshot.png)

The window shows a picture of the Ethernet port with two lights:

| Light | Red | Amber (blinking) | Green |
|---|---|---|---|
| **LINK** (left) | No cable plugged in | | Cable connected |
| **SHARE** (right) | Not sharing | Sharing, waiting for a device | A device got an IP address |

Under the picture it shows the device's IP address (for example `192.168.2.23`) and the Pi's gateway address (`192.168.2.1`).

## Setup

Needs Raspberry Pi OS Bookworm or newer (NetworkManager).

```bash
sudo apt install -y python3-tk
python3 eth_share.py
```

Click **Add desktop icon** once. After that, double-click the icon on the desktop to start it.

## Notes

- START and STOP may ask for your password.
- You can click START before plugging in a cable. The port turns on by itself when one is plugged in.
- If the Pi is getting its own internet through the Ethernet port (plugged into a router), the app warns you before taking that connection over.
- Devices on the port get addresses in `192.168.2.x`, so it doesn't clash with a Wi-Fi network on `192.168.1.x`.
- The plugged-in device uses whatever internet the Pi has. To share an iPhone's data, turn on **Route ALL Pi traffic** in [iPhone Tether](https://github.com/CharlesPhillips3/iphone-tether) first (TCP only).

## What it does under the hood

START creates a NetworkManager connection called `eth-share` on `eth0` with `ipv4.method shared` and the address `192.168.2.1/24`. NetworkManager then runs a DHCP server on the port and NATs traffic out the Pi's default route. STOP deletes that connection and reconnects `eth0` to its normal profile.

Manual equivalent:

```bash
sudo nmcli con add type ethernet ifname eth0 con-name eth-share \
  ipv4.method shared ipv4.addresses 192.168.2.1/24 ipv6.method disabled
sudo nmcli con up eth-share
# undo:
sudo nmcli con delete eth-share
```
