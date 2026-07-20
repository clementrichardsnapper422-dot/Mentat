# Mentat Desktop

A native Windows Electron shell for Mentat's local Control UI.

The desktop app does not move tools, memory, credentials, or the Gateway into a hosted web service. It opens the locally served Mentat UI in a dedicated `Mentat.exe` window and starts the local Gateway when needed.

## Development

```powershell
cd apps\mentat-desktop
npm install
npm start
```

Mentat must already be installed and configured:

```powershell
.\install.cmd -SkipDesktop
mentat setup
```

## Build the Windows installer

```powershell
cd apps\mentat-desktop
npm install
npm run dist
```

The NSIS installer is written to `apps\mentat-desktop\dist`.

## Runtime behavior

- loads only the configured local Gateway at `127.0.0.1`
- blocks renderer access to Node.js and Electron APIs
- opens non-local links in the default browser
- starts the Gateway when it is not already running
- stops the Gateway on exit only when the desktop app started it
- uses a single application instance
- provides menu commands for reload, Gateway restart, logs, zoom, full screen, and developer tools

The Windows app currently targets x64. The installer is unsigned until a Windows code-signing certificate is configured.
