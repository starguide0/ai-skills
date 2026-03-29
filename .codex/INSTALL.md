# Installing Skills for Codex

Enable ai-skills in Codex via native skill discovery. Just clone and symlink.

## Prerequisites

- Git

## Installation

1. **Clone the ai-skills repository:**
   ```bash
   git clone https://github.com/starguide0/ai-skills.git ~/.codex/ai-skills
   ```

2. **Create the skills symlink:**
   ```bash
   mkdir -p ~/.agents/skills
   ln -s ~/.codex/ai-skills/e2e_test ~/.agents/skills/e2e_test
   # Add other skills like `refresh_architecture` here if needed by duplicating the symlink command
   ```

   **Windows (PowerShell):**
   ```powershell
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
   cmd /c mklink /J "$env:USERPROFILE\.agents\skills\e2e_test" "$env:USERPROFILE\.codex\ai-skills\e2e_test"
   ```

3. **Restart Codex** (quit and relaunch the CLI) to discover the skills.

## Verify

```bash
ls -la ~/.agents/skills/e2e_test
```

You should see a symlink (or junction on Windows) pointing to your ai-skills e2e_test directory.

## Updating

```bash
cd ~/.codex/ai-skills && git pull
```

Skills update instantly through the symlink.

## Uninstalling

```bash
rm ~/.agents/skills/e2e_test
```

Optionally delete the clone: `rm -rf ~/.codex/ai-skills`.
