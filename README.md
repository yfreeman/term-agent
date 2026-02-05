# Term Agent

Stateless terminal agent for Claude Code using tmux as state store.

## Features

- **Stateless**: No local state - tmux is the database
- **Persistent**: Sessions survive agent restarts
- **Observable**: User can attach to any session anytime
- **Simple**: Clean Python API using libtmux

## Installation

### Using pipx (Recommended)

**From GitHub:**
```bash
# Latest version
pipx install git+https://github.com/yfreeman/term-agent.git

# Specific version/tag
pipx install git+https://github.com/yfreeman/term-agent.git@v0.1.0
```

**From local source (for development):**
```bash
# Editable install
pipx install -e /path/to/term-agent

# Or from current directory
pipx install -e .
```

**Update existing installation:**
```bash
pipx install --force git+https://github.com/yfreeman/term-agent.git
```

### Create shell alias (optional)

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
alias ta='term-agent'
```

Then reload:
```bash
source ~/.zshrc  # or ~/.bashrc
```

## Usage

### CLI Commands

```bash
# List all sessions
term-agent list

# Create new session (auto-generated name)
term-agent create

# Create session with specific name
term-agent create --name my-session

# Execute command in session
term-agent exec my-session "ls -la"

# Capture output from session
term-agent capture my-session

# Kill session
term-agent kill my-session
```

### JSON Output (for programmatic use)

```bash
term-agent --json list
term-agent --json create --name test
term-agent --json exec test "pwd"
term-agent --json capture test
```

### Attach to session manually

```bash
tmux attach -t <session-name>
# Detach with: Ctrl+b, d
```

## Architecture

```
Orchestrator → term-agent → tmux (state store)
                             ↓
                        User can attach
```

## Python API

```python
from term_agent.agent import TerminalAgent

agent = TerminalAgent()

# List sessions
sessions = agent.list_sessions()

# Create session
result = agent.get_or_create_session("my-session")

# Execute command
agent.execute_command("my-session", "ls -la")

# Capture output
output = agent.capture_output("my-session")
print(output["output"])
```

## Dev Container / CI Installation

**In a Dockerfile or install script:**
```dockerfile
# Install pipx if not present
RUN python3 -m pip install --user pipx && \
    python3 -m pipx ensurepath

# Install term-agent from GitHub
RUN pipx install git+https://github.com/yfreeman/term-agent.git

# Verify installation
RUN term-agent --help
```

**In a shell install script:**
```bash
#!/bin/bash
# install-term-agent.sh

set -e

echo "Installing term-agent..."

# Ensure pipx is available
if ! command -v pipx &> /dev/null; then
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
fi

# Install term-agent
pipx install git+https://github.com/yfreeman/term-agent.git

# Verify
term-agent --help

echo "✓ term-agent installed successfully"
```

**Example devcontainer.json:**
```json
{
  "name": "My Project",
  "image": "mcr.microsoft.com/devcontainers/python:3.11",
  "postCreateCommand": "pipx install git+https://github.com/yfreeman/term-agent.git",
  "features": {
    "ghcr.io/devcontainers-contrib/features/pipx:2": {}
  }
}
```

## Claude Code Skill

This project includes a Claude Code skill for interactive terminal session management.

### Installing the Skill

Symlink the skill directory to your Claude Code skills directory:

```bash
# From the term-agent directory
ln -s "$(pwd)/terminal-session-skill" ~/.claude/skills/terminal-session
```

### Verify Skill Installation

```bash
# Check the symlink
ls -la ~/.claude/skills/terminal-session

# Should show:
# terminal-session -> /path/to/term-agent/terminal-session-skill
```

### Using the Skill

Once installed, Claude Code will automatically use the skill for:
- Long-running commands (builds, tests, deployments)
- SSH connections to remote servers
- Background processes (dev servers, watchers)
- Interactive commands requiring user input

For detailed skill documentation, see [SKILL_INSTALLATION.md](./SKILL_INSTALLATION.md).

## Development

```bash
# Clone the repository
git clone https://github.com/yfreeman/term-agent.git
cd term-agent

# Install in development mode
pipx install -e . --force

# Run tests (TODO)
pytest
```
