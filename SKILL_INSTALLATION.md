# Installing the Terminal Session Manager Skill

## Quick Installation

Symlink the skill directory (not the .md file!) to your Claude Code skills directory:

```bash
# Symlink to global skills directory (recommended)
ln -s "$(pwd)/terminal-session-skill" ~/.claude/skills/terminal-session

# Or symlink to project-specific skills directory
ln -s "$(pwd)/terminal-session-skill" /path/to/your/project/.claude/skills/terminal-session
```

**Important**: The skill must be a directory containing `skill.md`, not a standalone `.md` file. Claude Code expects skills to be directories that can contain multiple files.

## Verify Installation

After copying, Claude Code will automatically discover the skill. You can verify by:

1. Starting a new Claude Code session
2. The skill should be listed in available skills
3. Claude Code will use it when appropriate for terminal/SSH/long-running commands

## Usage in Claude Code

Once installed, you can:

### Invoke Directly
```
User: "Start a development server in a tmux session"
Claude: [Uses terminal-session skill automatically]
```

### Request Long-Running Commands
```
User: "Run the full test suite and let me watch it"
Claude: [Creates tmux session, runs tests, tells you how to attach]
```

### SSH Operations
```
User: "Connect to prod-server and deploy the latest code"
Claude: [Creates SSH session, executes commands, captures output]
```

## Configuration

No configuration required! The skill uses the globally installed `term-agent` command.

### Prerequisites

Ensure `term-agent` is installed:

```bash
# Check installation
which term-agent

# If not installed, install from this directory
cd /Users/jfreeman1271/scripts/term-agent
pipx install -e .
```

### Optional: Shell Alias

For manual use, add to `~/.zshrc`:

```bash
alias ta='term-agent'
```

Then reload:
```bash
source ~/.zshrc
```

## Skill File Locations

Claude Code looks for skills in these locations (in order):

1. **Project-specific**: `./.claude/skills/`
2. **Global**: `~/.claude/skills/`

The skill will be available in any directory where Claude Code can find it.

## Testing the Skill

Test manually:

```bash
# List sessions
term-agent --json list

# Create test session
term-agent --json create --name test

# Execute command
term-agent --json exec test "echo hello"

# Capture output
term-agent --json capture test

# Clean up
term-agent kill test
```

## Uninstallation

To remove the skill:

```bash
# Remove the symlink
rm ~/.claude/skills/terminal-session
```

To uninstall term-agent:

```bash
pipx uninstall term-agent
```

## Troubleshooting

**Skill not found:**
- Verify symlink exists: `ls -la ~/.claude/skills/terminal-session`
- Verify it's a directory symlink, not a file
- Check directory contains `skill.md` file
- Restart Claude Code session

**term-agent command not found:**
- Install with `pipx install -e /Users/jfreeman1271/scripts/term-agent`
- Verify with `which term-agent`
- Check `~/.local/bin` is in your `$PATH`

**tmux not installed:**
```bash
# macOS
brew install tmux

# Ubuntu/Debian
sudo apt install tmux
```

## Skill Directory Structure

The proper structure is:

```
term-agent/
├── terminal-session-skill/     # Skill directory
│   └── skill.md               # Skill documentation
└── ...

~/.claude/skills/
└── terminal-session -> /path/to/term-agent/terminal-session-skill  # Symlink to directory
```

---

That's it! Symlink the `terminal-session-skill` directory to your Claude skills directory and start using persistent terminal sessions in Claude Code.
