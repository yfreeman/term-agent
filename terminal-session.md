# Terminal Session Manager Skill

## Overview

This skill enables interactive terminal session management through tmux with intelligent task type tracking. Create persistent, observable terminal sessions that survive across invocations. The system automatically handles timeouts and completion detection based on task type.

## When to Use This Skill

Use this skill when you need to:
- Run long-running commands (builds, tests, deployments)
- Establish SSH connections to remote servers
- Execute interactive commands that may require user input
- Start background processes (dev servers, watchers, daemons)
- Monitor command output over time
- Keep terminal sessions alive between Claude Code invocations
- Allow the user to attach and observe what's happening in real-time

## Task Types - CRITICAL CONCEPT

**YOU MUST determine the task type before creating a session or executing commands.** The task type controls timeout behavior and completion detection.

### Task Type Decision Tree

| Task Type | When to Use | Examples | Completion Behavior |
|-----------|-------------|----------|---------------------|
| **oneshot** | Commands that run once and complete | `npm run build`, `pytest`, `git clone`, `curl`, `ls`, `cat` | ✅ Wait for completion (default 30s timeout) |
| **background** | Long-running services/servers | `npm run dev`, `python manage.py runserver`, `rails server`, `flask run` | ⚠️ Does NOT wait - returns immediately |
| **watcher** | File watchers that run indefinitely | `jest --watch`, `npm run watch`, `nodemon`, `cargo watch` | ⚠️ Does NOT wait - returns immediately |
| **interactive** | Programs requiring user interaction | `ssh user@host`, `vim`, `python` (REPL), `psql`, `mysql` | ⏸️ Waits briefly, then tells user to attach |

### How to Determine Task Type

**Analyze the user's request and command:**

1. **Look for server/serve keywords** → `background`
   - "start the dev server"
   - "run the development server"
   - Commands: `npm start`, `yarn dev`, `python -m http.server`

2. **Look for watch keywords** → `watcher`
   - "watch for changes"
   - "automatically run tests"
   - Commands: `--watch`, `watch`, `nodemon`

3. **Look for SSH or interactive tools** → `interactive`
   - "SSH to the server"
   - "connect to database"
   - Commands: `ssh`, `vim`, `nano`, REPLs

4. **Build/test/one-time operations** → `oneshot` (default)
   - "run the tests"
   - "build the project"
   - "clone the repo"

### Examples of Task Type Selection

```
User: "Start the development server"
→ task_type: "background"
→ description: "Development server"

User: "Run the test suite"
→ task_type: "oneshot"
→ description: "Running test suite"

User: "SSH to prod-server and check logs"
→ task_type: "interactive"
→ description: "SSH connection to prod-server"

User: "Watch files and run tests automatically"
→ task_type: "watcher"
→ description: "Jest watch mode"
```

## Smart Output Reading - CRITICAL FOR CONTEXT MANAGEMENT

**The agent uses intelligent output extraction to minimize context usage while preserving critical information.**

### How It Works

Every command execution:
1. **Pipes output to log file** with unique marker
2. **On capture**: Reads from marker to end
3. **Analyzes line count**:
   - **<= 20 lines**: Returns all (small enough)
   - **> 20 lines**: Smart extraction

### Extraction Methods

You'll receive an `extraction_method` field that tells you what happened:

| Method | Meaning | Action |
|--------|---------|--------|
| **full** | All output returned (< 20 lines) | Use as-is |
| **first_last** | First 10 + last 10 lines | Likely success, check last lines for errors |
| **error_extraction_python_traceback** | Python error detected | Error found, context included |
| **error_extraction_generic_error** | Generic error detected | Error found, context included |
| **error_extraction_compilation_error** | Compilation error detected | Build failed, check output |
| **error_extraction_test_failure** | Test failure detected | Tests failed, see context |
| **capture_pane** | Fallback (no log file) | Old method, may be incomplete |

### Critical Fields in Capture Response

```json
{
  "status": "success",
  "output": ["line1", "line2", "..."],
  "line_count": 150,              // Total lines in full output
  "extraction_method": "first_last",
  "truncated": true,               // If true, there's more
  "message": "Output has 150 lines, showing 20 relevant lines"
}
```

### Decision Tree: Should You Read More?

**ALWAYS check these fields after capture:**

```python
# 1. Check if truncated
if result["truncated"]:
    # There's more output

    # 2. Check extraction method
    if result["extraction_method"].startswith("error_extraction"):
        # Error found - context should be sufficient
        # Parse the error and report to user

    elif result["extraction_method"] == "first_last":
        # Success likely - check last lines for confirmation
        last_lines = result["output"][-5:]

        if any("error" in line.lower() for line in last_lines):
            # Error mentioned - get full output
            capture_full()
        elif any("success" in line.lower() for line in last_lines):
            # Success confirmed - smart extraction was good
            pass
        else:
            # Ambiguous - might need full output
            # Decide based on task importance

    # 3. If line_count is reasonable, get full output
    if result["line_count"] < 200:
        # Not too much - safe to read full
        capture_full()
```

### When to Use `--full` Flag

Request full output when:

**1. Ambiguous smart extraction**
```bash
term-agent --json capture session --full
```
Use when first+last doesn't give clear success/failure.

**2. Debugging needed**
User asks "why did it fail?" - get full context.

**3. Line count is reasonable**
If `line_count < 100-200`, full output fits in context.

**4. Build/test summaries needed**
You need to count failures, parse all test results.

**5. Error context insufficient**
Smart extraction found error but you need more surrounding context.

### When NOT to Use `--full`

**DON'T request full output when:**

❌ **Line count > 500** - Too much context
❌ **Error extraction already clear** - Error + context is enough
❌ **Background/watcher tasks** - Ongoing output, not meaningful
❌ **User just wants confirmation** - Last lines show success/failure

### Example Workflows

#### Workflow 1: Build Command

```markdown
1. Execute build:
   term-agent --json exec build "npm run build"

2. Capture (smart):
   term-agent --json capture build

3. Check result:
   {
     "line_count": 245,
     "extraction_method": "first_last",
     "truncated": true,
     "output": [
       "Starting build...",
       "Compiling...",
       ...
       "Build completed successfully!",
       "Output: dist/"
     ]
   }

4. Decision: Last lines show success
   → No need for full output
   → Report success to user
```

#### Workflow 2: Test Failure

```markdown
1. Execute tests:
   term-agent --json exec test "pytest tests/"

2. Capture (smart):
   term-agent --json capture test

3. Check result:
   {
     "line_count": 380,
     "extraction_method": "error_extraction_test_failure",
     "truncated": true,
     "output": [
       "test_user.py::test_login PASSED",
       "test_user.py::test_signup FAILED",
       "...",
       "AssertionError: Expected 200, got 400",
       "..."
     ]
   }

4. Decision: Error extraction found the failure
   → Error context is sufficient
   → Parse the error and report to user
   → Maybe show relevant lines around failure
```

#### Workflow 3: Ambiguous Compilation

```markdown
1. Execute compilation:
   term-agent --json exec compile "make"

2. Capture (smart):
   term-agent --json capture compile

3. Check result:
   {
     "line_count": 120,
     "extraction_method": "first_last",
     "truncated": true,
     "output": [
       "gcc -o app main.c",
       "Compiling...",
       ...
       "ld: library not found",
       "make: *** [app] Error 1"
     ]
   }

4. Decision: Last lines show error, but truncated
   → line_count (120) is reasonable
   → Get full output for complete error context

5. Get full:
   term-agent --json capture compile --full

6. Now parse full output for all errors
```

#### Workflow 4: Long Log Output

```markdown
1. Execute log tail:
   term-agent --json exec logs "tail -1000 /var/log/app.log"

2. Capture (smart):
   term-agent --json capture logs

3. Check result:
   {
     "line_count": 1000,
     "extraction_method": "first_last",
     "truncated": true
   }

4. Decision: 1000 lines is too much
   → Don't request full
   → Instead ask user what they're looking for
   → "The log has 1000 lines. Are you looking for specific errors?"
   → Then grep/filter if needed
```

### Advanced: Incremental Reading

For very long output, you can read chunks:

```bash
# Smart extraction first
term-agent --json capture session

# If you need specific sections, use line ranges
# (This falls back to capture_pane, but useful for targeted reading)
term-agent --json capture session --start 0 --end 50
term-agent --json capture session --start 450 --end 500
```

### Smart Reading Summary

**Key Principles:**
1. **Always check `truncated` and `extraction_method`**
2. **Error extractions are usually sufficient**
3. **Use --full judiciously** (only when line_count < 200 or ambiguous)
4. **For massive output** (>500 lines), don't read full - ask user what they need
5. **Report what you found**, don't just dump output

**Context Management:**
- Smart reading saves 50-90% of context tokens
- Errors are detected automatically with surrounding context
- You get actionable information without overwhelming context
- Only read full when truly necessary

## Available Commands

All commands use the `term-agent` CLI with `--json` flag for programmatic output.

### 1. List Sessions

```bash
term-agent --json list
```

**Output:**
```json
{
  "status": "success",
  "sessions": [
    {"name": "session-name", "id": "$0", "windows": 1}
  ]
}
```

### 2. Create Session with Task Type

```bash
# With task type and description (RECOMMENDED)
term-agent --json create --name my-session --task-type oneshot --description "Building application"

# Minimal
term-agent --json create --name my-session
```

**Output:**
```json
{
  "status": "success",
  "action": "created",
  "session_name": "my-session",
  "session_id": "$1",
  "windows": 1,
  "task_type": "oneshot",
  "description": "Building application"
}
```

### 3. Execute Command

```bash
term-agent --json exec <session-name> "<command>"
```

**Output:**
```json
{
  "status": "success",
  "session_name": "my-session",
  "window_name": "zsh",
  "pane_id": "%1",
  "message": "Command sent"
}
```

### 4. Wait for Completion

**NEW:** Intelligent waiting based on task type metadata.

```bash
# Wait with default timeout (30s), respects metadata
term-agent --json wait <session-name>

# Custom timeout
term-agent --json wait <session-name> --timeout 60

# Ignore metadata and force wait
term-agent --json wait <session-name> --no-respect-metadata
```

**Output (completed):**
```json
{
  "status": "completed",
  "session_name": "build-task",
  "output": ["..."],
  "elapsed_time": 12.5,
  "timed_out": false
}
```

**Output (timeout):**
```json
{
  "status": "timeout",
  "session_name": "build-task",
  "output": ["..."],
  "elapsed_time": 30.0,
  "timed_out": true,
  "message": "Command still running after 30s (check again later with 'capture' or 'wait')"
}
```

**Output (background/watcher task):**
```json
{
  "status": "running",
  "session_name": "dev-server",
  "output": ["..."],
  "task_type": "background",
  "message": "Task type 'background' - not waiting for completion"
}
```

### 5. Capture Output (Smart Reading)

```bash
# Smart reading (default) - Intelligently extracts relevant output
term-agent --json capture <session-name>

# Full output - Returns everything (use sparingly)
term-agent --json capture <session-name> --full
```

**Output (Smart Reading):**
```json
{
  "status": "success",
  "session_name": "my-session",
  "log_file": "/tmp/term-agent-logs/my-session.log",
  "marker_id": "abc123",
  "output": ["line1", "line2", "..."],
  "line_count": 150,
  "extraction_method": "first_last",
  "truncated": true,
  "message": "Output has 150 lines, showing 20 relevant lines"
}
```

**Output (Full):**
```json
{
  "status": "success",
  "session_name": "my-session",
  "output": ["all 150 lines..."],
  "line_count": 150,
  "extraction_method": "full",
  "truncated": false,
  "forced_full": true
}
```

### 6. Metadata Management

```bash
# Get metadata
term-agent --json metadata <session-name>

# Set metadata
term-agent --json metadata <session-name> --set --task-type background --description "Dev server"
```

### 7. Kill Session

```bash
term-agent --json kill <session-name>
```

## Workflow Patterns

### Pattern 1: One-Shot Command (Build/Test) with Smart Reading

```markdown
1. Determine task type: "oneshot"

2. Create session:
   ```bash
   term-agent --json create --name build-app --task-type oneshot --description "Building application"
   ```

3. Execute command:
   ```bash
   term-agent --json exec build-app "npm run build"
   ```

4. Wait for completion (respects task_type):
   ```bash
   term-agent --json wait build-app --timeout 120
   ```

5. Capture output (smart reading):
   ```bash
   term-agent --json capture build-app
   ```

6. Check result:
   ```python
   if result["extraction_method"].startswith("error_extraction"):
       # Error detected - report to user
       print(f"Build failed with {result['extraction_method']}")
       show_error_context(result["output"])

   elif result["truncated"]:
       # Check last lines
       if "success" in result["output"][-1].lower():
           print("Build completed successfully!")
       elif result["line_count"] < 200:
           # Get full output for detailed analysis
           full_result = capture_with_full_flag()
   else:
       # Full output received (< 20 lines)
       print("Build output:")
       print(result["output"])
   ```

7. Clean up:
   ```bash
   term-agent --json kill build-app
   ```
```

### Pattern 2: Background Server

```markdown
1. Determine task type: "background"

2. Create session:
   ```bash
   term-agent --json create --name dev-server --task-type background --description "Development server"
   ```

3. Execute command:
   ```bash
   term-agent --json exec dev-server "npm run dev"
   ```

4. DON'T wait (it will return immediately):
   ```bash
   term-agent --json wait dev-server
   ```
   Result: {"status": "running", "message": "Task type 'background' - not waiting for completion"}

5. Tell user:
   > Development server started in tmux session 'dev-server'
   > Attach to watch: tmux attach -t dev-server
   > The server will keep running in the background.

6. DON'T kill session - it should stay alive
```

### Pattern 3: Interactive SSH

```markdown
1. Determine task type: "interactive"

2. Create session:
   ```bash
   term-agent --json create --name ssh-prod --task-type interactive --description "SSH to production"
   ```

3. Connect:
   ```bash
   term-agent --json exec ssh-prod "ssh user@prod-server"
   ```

4. Wait briefly for connection:
   ```bash
   term-agent --json wait ssh-prod --timeout 5
   ```

5. Capture to see if connected:
   ```bash
   term-agent --json capture ssh-prod
   ```

6. Send commands:
   ```bash
   term-agent --json exec ssh-prod "cd /app && tail -f logs/app.log"
   ```

7. Tell user:
   > Connected to prod-server. Attach to interact: tmux attach -t ssh-prod
```

### Pattern 4: File Watcher

```markdown
1. Determine task type: "watcher"

2. Create session:
   ```bash
   term-agent --json create --name test-watcher --task-type watcher --description "Jest watch mode"
   ```

3. Start watcher:
   ```bash
   term-agent --json exec test-watcher "npm run test:watch"
   ```

4. Wait (returns immediately):
   ```bash
   term-agent --json wait test-watcher
   ```

5. Capture initial output:
   ```bash
   term-agent --json capture test-watcher
   ```

6. Tell user:
   > Test watcher started in session 'test-watcher'
   > It will automatically run tests when files change.
   > Attach to watch: tmux attach -t test-watcher
```

## Important Guidelines

### Always Set Task Type

**ALWAYS** provide `--task-type` and `--description` when creating sessions:

```bash
# ✅ GOOD
term-agent --json create --name build --task-type oneshot --description "Building frontend"

# ❌ BAD
term-agent --json create --name build
```

### Respect Task Type Behavior

- **oneshot**: Use `wait` command, handle timeout, parse results
- **background**: Don't wait, tell user how to attach, don't kill session
- **watcher**: Don't wait, capture initial output, don't kill session
- **interactive**: Brief wait, tell user to attach for interaction

### Timeout Handling

When `wait` returns `status: "timeout"`:

```python
if result["status"] == "timeout":
    # Command is STILL RUNNING in tmux
    # User can:
    # 1. Attach to watch: tmux attach -t <session>
    # 2. Check later: term-agent wait <session> (resume waiting)
    # 3. Capture current state: term-agent capture <session>
```

### User Communication

Always tell the user:
1. What session was created and its task type
2. How to attach: `tmux attach -t <session-name>`
3. How to detach: `Ctrl+b, d`
4. Whether the task is still running or completed
5. For background/watcher tasks: "Session will keep running"

### Session Lifecycle

- **oneshot**: Create → Execute → Wait → Kill (after completion)
- **background**: Create → Execute → Keep alive (don't kill)
- **watcher**: Create → Execute → Keep alive (don't kill)
- **interactive**: Create → Execute → User controls (may kill later)

## Example Conversations

### User: "Run the test suite"

```
Claude: I'll run the test suite in a tmux session.

[Determine: task_type="oneshot"]
[Call: term-agent --json create --name test-run --task-type oneshot --description "Running test suite"]
[Call: term-agent --json exec test-run "pytest tests/ -v"]
[Call: term-agent --json wait test-run --timeout 60]

[If completed]:
The tests completed in 23.5s. Here are the results:
[Parse and summarize output]

[If timeout]:
The tests are still running after 60s. You can attach to watch progress:
    tmux attach -t test-run

I'll check again in a moment...
[Call: term-agent --json wait test-run --timeout 60 again]
```

### User: "Start the development server"

```
Claude: I'll start the development server in a tmux session.

[Determine: task_type="background"]
[Call: term-agent --json create --name dev-server --task-type background --description "Development server"]
[Call: term-agent --json exec dev-server "npm run dev"]
[Call: term-agent --json wait dev-server]
[Returns immediately with status="running"]
[Call: term-agent --json capture dev-server to get initial output]

Development server started in session 'dev-server'!

Initial output shows:
[Show relevant startup lines]

The server is running in the background. To watch it:
    tmux attach -t dev-server

Detach anytime with: Ctrl+b, d

The session will stay alive even if you close this conversation.
```

### User: "SSH to the server and check disk usage"

```
Claude: I'll connect to the server via SSH.

[Determine: task_type="interactive"]
[Call: term-agent --json create --name ssh-server --task-type interactive --description "SSH to server"]
[Call: term-agent --json exec ssh-server "ssh user@server"]
[Call: term-agent --json wait ssh-server --timeout 5]
[Call: term-agent --json capture ssh-server to check connection]

Connected to server! Now checking disk usage...
[Call: term-agent --json exec ssh-server "df -h"]
[Wait and capture]

Disk usage:
[Parse and show output]

SSH session 'ssh-server' is still connected. To interact directly:
    tmux attach -t ssh-server
```

## Advantages Over Direct Bash Tool

| Feature | term-agent | Bash Tool |
|---------|-----------|-----------|
| **Persistence** | Sessions survive restarts | Process dies when done |
| **Observation** | User can attach anytime | No visibility |
| **Interactive** | Can send multiple commands | One-shot execution |
| **Long-running** | Perfect for builds, servers | Times out |
| **State** | Maintains shell state (cwd, env) | Each call is fresh |
| **Timeout handling** | Resume waiting later | Can't resume |
| **Task awareness** | Knows not to wait for servers | Treats all the same |

## Installation

The term-agent should be installed via pipx:

```bash
cd /Users/jfreeman1271/scripts/term-agent
pipx install -e .
```

Verify installation:
```bash
term-agent --help
```

## Troubleshooting

**"Command timed out but should have completed"**
- Check if task_type is correct (should be "oneshot")
- Increase timeout: `--timeout 120`
- Use `capture` to see current state

**"Background server immediately stops"**
- Ensure task_type="background"
- Check if command needs to run in foreground
- Attach to see error: `tmux attach -t <session>`

**"Wait returns immediately for build command"**
- Check metadata: `term-agent metadata <session>`
- If wrong task_type, set it: `term-agent metadata <session> --set --task-type oneshot`
- Or force wait: `term-agent wait <session> --no-respect-metadata`

---

## Best Practices for Context Management

### Always Follow This Pattern

**1. Capture with smart reading first (default)**
```bash
result = term-agent --json capture session
```

**2. Check extraction_method and truncated**
```python
if result["truncated"]:
    if result["extraction_method"].startswith("error_extraction"):
        # Error found, context included
        analyze_and_report_error(result["output"])
    else:
        # Check if you need more
        decide_if_full_needed(result)
```

**3. Only use --full when necessary**
```bash
# When: line_count < 200 AND ambiguous result
if result["line_count"] < 200 and is_ambiguous(result):
    full_result = term-agent --json capture session --full
```

**4. For huge output (>500 lines), don't read full**
```python
if result["line_count"] > 500:
    # Instead: Ask user what they're looking for
    # Or: Use grep/filtering
    # Or: Just report summary from first+last
```

### Context Efficiency Examples

**Good Context Usage ✅**
```
Build with 300 lines:
- Smart: 20 lines captured, error found → Report to user
- Saved: 280 lines of context
```

**Bad Context Usage ❌**
```
Build with 300 lines:
- Requested full without checking
- Dumped 300 lines into context
- Most lines were not relevant
```

### Error Handling Priority

When you see truncated output:

**Priority 1: Error extractions** - Trust them
- `error_extraction_*` methods have found and contextualized the error
- Use the provided context to report the issue
- No need for full output

**Priority 2: Small truncations** (< 100 lines)
- Reasonable to get full output
- Won't overwhelm context

**Priority 3: Medium truncations** (100-300 lines)
- Check last lines for clear success/failure
- Only get full if ambiguous

**Priority 4: Large truncations** (> 300 lines)
- Don't request full
- Work with smart extraction
- Ask user for clarification if needed

## Summary

The Terminal Session Manager skill provides persistent, observable terminal sessions with intelligent task type awareness and smart output reading.

**YOU MUST:**
- Determine the task type from the user's request
- Check `truncated` and `extraction_method` after capture
- Use `--full` flag judiciously (< 200 lines, ambiguous cases only)
- Trust error extractions - they include necessary context
- Manage context efficiently - don't dump massive outputs

**Remember**:
- **Task types**: oneshot = wait for completion, background/watcher = don't wait, interactive = brief wait
- **Smart reading**: Saves 50-90% context, detects errors automatically
- **Full output**: Only when line_count < 200 AND result is ambiguous
- **Context is precious**: Smart extraction is your friend
