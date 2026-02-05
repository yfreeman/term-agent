# Term Agent

Stateless terminal agent for Claude Code using tmux as state store.

## Features

- **Stateless**: No local state - tmux is the database
- **Persistent**: Sessions survive agent restarts
- **Observable**: User can attach to any session anytime
- **Simple**: Clean Python API using libtmux

## Installation

### Using pipx (Recommended)

```bash
# From this directory
pipx install -e .

# Or install from path
pipx install /Users/jfreeman1271/scripts/term-agent
```

### Create shell alias (optional)

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
alias ta='term-agent'
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

## Development

```bash
# Install in development mode
pipx install -e . --force

# Run tests (TODO)
pytest
```
