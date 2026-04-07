# Protocol Bridge

This is a vendored local copy of the published `spacenav-ws` bridge, adapted for this workspace.

## What it does

- listens on `https://127.51.68.120:8181`
- exposes `GET /3dconnexion/nlproxy`
- accepts the Onshape WAMP websocket
- reads SpaceMouse events from `spacenavd` over `/var/run/spnav.sock`
- writes `view.affine`, `view.extents`, and motion state back to Onshape

## Setup

```bash
cd /home/benlevin/spacemouse-onshape-linux/protocol_bridge
./setup_bridge.sh
```

Then open:

```text
https://127.51.68.120:8181
```

and allow the self-signed certificate exception once in the browser.

## Startup

`setup_bridge.sh` installs and enables a user-level systemd service:

```bash
systemctl --user status spacemouse-onshape-bridge.service --no-pager
journalctl --user -u spacemouse-onshape-bridge.service -f
```

If you want to run it manually instead:

```bash
cd /home/benlevin/spacemouse-onshape-linux/protocol_bridge
./run_bridge.sh
```

## Browser side

Use the userscript from:

```text
/home/benlevin/spacemouse-onshape-linux/onshape-platform-patch.user.js
```

The installer prints the Tampermonkey / Violentmonkey steps at the end.
