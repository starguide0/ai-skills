# Installing Skills for OpenCode

## Prerequisites

- [OpenCode.ai](https://opencode.ai) installed
- Git installed

## Installation Steps

### 1. Clone AI-Skills

```bash
git clone https://github.com/starguide0/ai-skills.git ~/.config/opencode/ai-skills
```

### 2. Register the Plugin (If any global plugins exist)

> **Note**: If `ai-skills` provides a global OpenCode plugin, link it here:
> ```bash
> mkdir -p ~/.config/opencode/plugins
> rm -f ~/.config/opencode/plugins/ai-skills.js
> ln -s ~/.config/opencode/ai-skills/.opencode/plugins/ai-skills.js ~/.config/opencode/plugins/ai-skills.js
> ```

### 3. Symlink Skills

Create a symlink so OpenCode's native skill tool discovers the specific skills (e.g., `e2e_test`):

```bash
mkdir -p ~/.config/opencode/skills
rm -rf ~/.config/opencode/skills/e2e_test
ln -s ~/.config/opencode/ai-skills/e2e_test ~/.config/opencode/skills/e2e_test
```

### 4. Restart OpenCode

Restart OpenCode.

## Usage

### Finding Skills

Use OpenCode's native `skill` tool to list available skills:

```
use skill tool to list skills
```

### Loading a Skill

Use OpenCode's native `skill` tool to load a specific skill:

```
use skill tool to load e2e_test
```

## Updating

```bash
cd ~/.config/opencode/ai-skills
git pull
```
