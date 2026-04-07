# Userscript Setup

Use this instead of the Chrome extension wrapper. The bridge logs show discovery succeeds, but the extension patch still does not make Onshape open the websocket. The known working delivery path is a userscript that runs at `document-start`.

The userscript is configured to match:

- `https://*.onshape.com/documents/*`

so it covers tenant-hosted URLs like:

- `https://formulatrix.onshape.com/documents/...`

## Install

1. Install `Tampermonkey` or `Violentmonkey` in Chrome or Firefox.
2. Create a new userscript.
3. Paste the contents of:

`/home/benlevin/spacemouse-onshape-linux/onshape-platform-patch.user.js`

4. Save it.
5. Disable or remove the unpacked Chrome extension version of the patch to avoid conflicts.
6. Keep the protocol bridge running:

```bash
cd /home/benlevin/spacemouse-onshape-linux/protocol_bridge
./setup_bridge.sh
```

7. Open `https://127.51.68.120:8181` once and accept the certificate exception if needed.
8. Refresh Onshape.

## Firefox notes

Firefox can use the same bridge and userscript path.

1. Install `Tampermonkey` or `Violentmonkey` in Firefox.
2. Add `/home/benlevin/spacemouse-onshape-linux/onshape-platform-patch.user.js` as a userscript.
3. Visit `https://127.51.68.120:8181` in Firefox directly.
4. Accept the certificate exception in Firefox itself.
5. Open your Onshape document at `https://formulatrix.onshape.com/documents/...`
6. Refresh once after the userscript is enabled.

If Firefox still does not connect, the first thing to check is whether the userscript manager reports the script as active on the document page.

## Expected signal

If the userscript lands correctly, the bridge log should advance beyond discovery and start showing:

- websocket connect
- WAMP messages
- `3dx_rpc:create`
- controller creation / subscribe
