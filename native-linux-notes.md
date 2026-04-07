# Native Linux Fix

`spacenavd.service` is currently running as a system service and its journal shows repeated X11 failures like:

- `XAUTHORITY=/root/.Xauthority`
- `failed to open X11 display ":0.0"`

That means the daemon is alive and reading the device, but its X11 bridge is not attaching to your desktop session. The user service below starts the X11 bridge from your own session instead:

- `/home/benlevin/.config/systemd/user/spacenav-x11-bridge.service`

To enable it:

1. `systemctl --user daemon-reload`
2. `systemctl --user enable --now spacenav-x11-bridge.service`

This is mainly for native Linux/X11 applications. Onshape in Chrome still needs the WebHID workaround because the supported 3Dconnexion Onshape path does not include Linux.
