# Onshape SpaceMouse Linux Bridge

This project now uses a protocol bridge instead of synthetic mouse gestures.

## Architecture

1. Chrome patches the Onshape page so it exposes the Windows 3Dconnexion client path on Linux.
2. A local TLS server on `https://127.51.68.120:8181` answers Onshape's `3dconnexion/nlproxy` discovery call.
3. Onshape opens a WAMP websocket to the bridge.
4. The bridge reads `spacenavd` events from `/var/run/spnav.sock` and writes camera state back through Onshape's 3Dconnexion protocol.

## Files

- Chrome patch extension: `/home/benlevin/spacemouse-onshape-linux`
- Python protocol bridge: `/home/benlevin/spacemouse-onshape-linux/protocol_bridge`
- udev rule for WebHID access if you still need raw HID experiments: `/home/benlevin/spacemouse-onshape-linux/99-spacemouse-webhid.rules`

## Install

1. Keep `spacenavd` running.
2. Load the unpacked Chrome extension from `/home/benlevin/spacemouse-onshape-linux`.
3. Start the local bridge from the `protocol_bridge` directory.
4. Open `https://127.51.68.120:8181` once and allow the certificate exception.
5. Refresh Onshape.

## Current status

The old WebHID gesture shim has been removed in favor of the native protocol direction. The remaining work is in the bridge runtime setup and verification.
