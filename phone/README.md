# phone

The agent's phone: [mobile-mcp](https://github.com/mobile-next/mobile-mcp) (pinned, Apache-2.0) driving an Android device over adb. In the local stack the device is [Redroid](https://github.com/remote-android/redroid-doc) (Android in a container).

- **Token required:** the MCP answers only with `Authorization: Bearer $MOBILEMCP_AUTH`, and it lives on the agent's internal network.
- **Closed tool list:** the agent gets only the tools to see and drive the screen and open apps or links (see `agent/config/config.yaml`). Installing or uninstalling apps, clearing app data, batch commands, the clipboard, device logs, recordings, location spoofing and the mobilenext cloud are left out on purpose.
- **Android needs a VM:** Redroid runs privileged and needs the `binder` kernel module on the host, so the phone is a higher-tier feature that runs on a dedicated VM, never in a shared cluster.

| Variable | Meaning |
|---|---|
| `MOBILEMCP_AUTH` | required; the Bearer token the agent sends |
| `PHONE_ADB_TARGET` | the device, default `android:5555` |
| `PHONE_LISTEN` | where the MCP listens, default `0.0.0.0:3000` |

Host prerequisite for Redroid (Ubuntu): `sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"` (or a kernel with binderfs).
