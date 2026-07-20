# Native Windows installation

Mentat supports Windows 10 and Windows 11 directly through Windows PowerShell 5.1 or PowerShell 7. WSL is not required.

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

`install.cmd` launches the checked-in PowerShell installer with an execution-policy bypass for that process only. It does not change the computer's permanent PowerShell execution policy.

Installer options:

```powershell
.\install.cmd -SkipUI
.\install.cmd -SkipDeps
.\install.cmd -NoPath
```

Open a new PowerShell window after installation:

```powershell
mentat setup
mentat start
mentat chat
```

## Windows locations

Mentat uses per-user Windows locations:

```text
%LOCALAPPDATA%\Mentat\bin       command wrappers
%LOCALAPPDATA%\Mentat\config    encrypted configuration
%LOCALAPPDATA%\Mentat\state     PID files and logs
%LOCALAPPDATA%\Mentat\npm       user-local pnpm installation when needed
```

The installer adds `%LOCALAPPDATA%\Mentat\bin` to the user `PATH`. It does not require Administrator access.

## Credential protection

The Vast API key is never written as plaintext to the configuration file. PowerShell protects it with Windows Data Protection API through `ConvertFrom-SecureString`.

The encrypted value can only be decrypted by the same Windows user profile on the same Windows installation. Moving `config.json` to another account or computer will not make the key usable there; run `mentat setup vast` again instead.

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

To reinstall the command and dependencies:

```powershell
.\install.cmd
```

The installer does not use WSL, Git Bash, Cygwin, or a Unix compatibility layer.

## Uninstall

Keep encrypted configuration:

```powershell
mentat uninstall
```

Remove the command, encrypted configuration, and local state:

```powershell
mentat uninstall --purge
```

The source checkout is not deleted automatically.
