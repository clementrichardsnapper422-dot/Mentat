# Native Windows installation and desktop app

Mentat supports Windows 10 and Windows 11 directly through Windows PowerShell 5.1 or PowerShell 7. WSL is not required.

The normal installation produces both:

- the `mentat` command-line interface
- a native `Mentat.exe` desktop application with Desktop and Start Menu shortcuts

## Requirements

Install these Windows applications and make sure they are available on `PATH`:

- Git for Windows
- Node.js 24.15+ recommended, or 22.22.3+ / 25.9+
- Python 3.11+
- Ollama only when using the Ollama Cloud fallback

When installing Python, enable **Add Python to PATH**. The installer supports either the `py -3` launcher or `python.exe`.

## Install

Open PowerShell:

```powershell
git clone https://github.com/clementrichardsnapper422-dot/Mentat.git
cd Mentat
.\install.cmd
```

`install.cmd` launches the checked-in PowerShell installer with an execution-policy bypass for that process only. It does not change the permanent PowerShell execution policy.

The installer builds an NSIS installer locally, installs Mentat per-user, and creates Desktop and Start Menu shortcuts. Administrator access is not required.

Installer options:

```powershell
.\install.cmd -SkipUI
.\install.cmd -SkipDeps
.\install.cmd -SkipDesktop
.\install.cmd -NoPath
```

Use `-SkipDesktop` to install only the command-line runtime without building or installing `Mentat.exe`.

## First launch

Open a new PowerShell window and configure Mentat:

```powershell
mentat setup
```

Then launch **Mentat** from the Desktop or Start Menu.

The desktop application will:

1. read the existing per-user Mentat configuration
2. check the configured local Gateway port
3. start the Gateway when it is not already running
4. wait for the Gateway to become ready
5. open the Control UI inside its own `Mentat.exe` window

Command-line chat remains available:

```powershell
mentat start
mentat chat
```

## Desktop security model

The Electron renderer is deliberately restricted:

- Node.js integration is disabled
- context isolation is enabled
- renderer sandboxing is enabled
- the window may navigate only to the configured `127.0.0.1` Gateway origin
- outside links open in the default browser
- only one desktop app instance is allowed

The desktop app is a shell around the local Gateway. It does not put local tools, memory, or credentials into a hosted Electron service.

If the Gateway was already running before the app opened, closing the app leaves it running. If the app started the Gateway, closing the app stops it.

The application menu includes:

- reload
- restart Gateway
- open Gateway logs
- zoom controls
- full screen
- developer tools

## Windows locations

Mentat uses per-user Windows locations:

```text
%LOCALAPPDATA%\Mentat\bin       command wrappers
%LOCALAPPDATA%\Mentat\config    encrypted configuration
%LOCALAPPDATA%\Mentat\state     PID files and logs
%LOCALAPPDATA%\Mentat\npm       user-local pnpm installation when needed
%LOCALAPPDATA%\Programs\Mentat   installed Mentat.exe application
```

The source-built installer is written to:

```text
apps\mentat-desktop\dist\Mentat-Setup-0.1.0.exe
```

## Credential protection

The Vast API key is never written as plaintext to the configuration file. PowerShell protects it with Windows Data Protection API through `ConvertFrom-SecureString`.

The encrypted value can only be decrypted by the same Windows user profile on the same Windows installation. Moving `config.json` to another account or computer will not make the key usable there; run `mentat setup vast` again instead.

The desktop app receives the decrypted key only through the local Gateway process environment when required.

## Code signing

The first locally built desktop installer is unsigned. Windows may show an unknown-publisher or SmartScreen warning.

Production distribution should add an Authenticode code-signing certificate and sign both the NSIS installer and `Mentat.exe`. The current build deliberately does not invent or embed a signing identity.

## Everyday commands

```powershell
mentat start
mentat stop
mentat restart
mentat status
mentat chat
mentat chat "Review this repository"
mentat logs
mentat doctor
mentat update
```

Run in the foreground while troubleshooting:

```powershell
mentat start --foreground
```

## Vast endpoint controls

```powershell
mentat vast estimate --hourly-price 28 --hours 2
mentat vast create --accept-test-worker-cost
mentat vast status
mentat vast test
mentat vast warm
mentat vast cool
mentat vast destroy --confirm
```

Paid operations keep the same explicit acknowledgement and confirmation gates used on macOS and Linux.

## Rebuild only the desktop installer

```powershell
cd apps\mentat-desktop
npm install
npm run dist
```

The generated installer is placed under `dist`.

## Troubleshooting

Run:

```powershell
mentat doctor
mentat status
mentat logs --no-follow
```

When `mentat` is not found, open a new PowerShell window first. To inspect the user path:

```powershell
[Environment]::GetEnvironmentVariable('Path', 'User')
```

To rebuild and reinstall everything:

```powershell
.\install.cmd
```

When the desktop window reports that setup is required:

```powershell
mentat setup
```

When the desktop window cannot reach the Gateway, use **Mentat → Open Gateway Logs**, or run:

```powershell
mentat logs --no-follow
```

The installer does not use WSL, Git Bash, Cygwin, or a Unix compatibility layer.

## Uninstall

Uninstall the desktop app from:

```text
Windows Settings → Apps → Installed apps → Mentat
```

Keep the command-line encrypted configuration:

```powershell
mentat uninstall
```

Remove the command, encrypted configuration, and local state:

```powershell
mentat uninstall --purge
```

The source checkout is not deleted automatically.
