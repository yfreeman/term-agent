"""Core terminal agent logic using libtmux."""

import uuid
import time
import re
import os
import subprocess
from typing import Optional, Dict, Any, List, Tuple
import libtmux
from libtmux._internal.query_list import ObjectDoesNotExist


class TerminalAgent:
    """Stateless terminal agent that uses tmux as state store."""

    # Valid task types - determined by the skill, not the agent
    TASK_TYPES = ["interactive", "background", "watcher", "oneshot"]

    def __init__(self, log_dir: Optional[str] = None):
        self.server = libtmux.Server()

        # Determine log directory with priority:
        # 1. Explicit parameter
        # 2. Environment variable TERM_AGENT_LOG_DIR
        # 3. Project-local: ./.term-agent/logs (if in git repo or has .term-agent)
        # 4. User home: ~/.term-agent/logs (default)
        if log_dir:
            self.log_dir = log_dir
        elif os.environ.get("TERM_AGENT_LOG_DIR"):
            self.log_dir = os.environ["TERM_AGENT_LOG_DIR"]
        elif self._is_project_directory():
            self.log_dir = os.path.join(os.getcwd(), ".term-agent", "logs")
        else:
            self.log_dir = os.path.expanduser("~/.term-agent/logs")

        # Create directory with proper permissions (755)
        try:
            os.makedirs(self.log_dir, mode=0o755, exist_ok=True)

            # If using project-local logs, ensure .gitignore exists
            if ".term-agent" in self.log_dir and os.path.exists(os.path.join(os.getcwd(), ".git")):
                self._ensure_gitignore()
        except PermissionError as e:
            # Fall back to /tmp if permission denied
            self.log_dir = "/tmp/term-agent-logs"
            os.makedirs(self.log_dir, mode=0o755, exist_ok=True)

    def _ensure_gitignore(self):
        """Ensure .term-agent directory is in .gitignore.

        Adds .term-agent/ to .gitignore if not already present.
        """
        gitignore_path = os.path.join(os.getcwd(), ".gitignore")

        try:
            # Read existing .gitignore
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r") as f:
                    content = f.read()

                # Check if .term-agent already ignored
                if ".term-agent" in content or ".term-agent/" in content:
                    return
            else:
                content = ""

            # Append .term-agent/ to .gitignore
            with open(gitignore_path, "a") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write("\n# Term Agent logs\n.term-agent/\n")
        except (PermissionError, IOError):
            # Ignore errors - not critical
            pass

    def _is_project_directory(self) -> bool:
        """Check if current directory is a project directory.

        Returns True if:
        - .git directory exists
        - .term-agent directory exists
        - pyproject.toml, package.json, or Cargo.toml exists
        """
        cwd = os.getcwd()

        indicators = [
            ".git",
            ".term-agent",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "pom.xml"
        ]

        return any(os.path.exists(os.path.join(cwd, indicator)) for indicator in indicators)

    def set_metadata(
        self,
        session_name: str,
        task_type: Optional[str] = None,
        description: Optional[str] = None,
        window_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Set metadata on session or window using tmux user options.

        Args:
            session_name: Name of tmux session
            task_type: Type of task (interactive, background, watcher, oneshot)
            description: Human-readable description
            window_name: Optional window name (sets on session if not provided)

        Returns:
            Dict with operation status
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Target session or window
        if window_name:
            try:
                target = session.windows.get(window_name=window_name)
            except ObjectDoesNotExist:
                return {
                    "status": "error",
                    "message": f"Window '{window_name}' not found"
                }
        else:
            target = session

        # Validate and set task_type
        if task_type:
            if task_type not in self.TASK_TYPES:
                return {
                    "status": "error",
                    "message": f"Invalid task_type '{task_type}'. Must be one of: {', '.join(self.TASK_TYPES)}"
                }
            target.set_option("@task_type", task_type, global_=False)

        # Set description
        if description:
            target.set_option("@description", description, global_=False)

        # Set timestamp and creator
        target.set_option("@created_at", str(int(time.time())), global_=False)
        target.set_option("@created_by", "term-agent", global_=False)

        return {
            "status": "success",
            "message": "Metadata set",
            "task_type": task_type,
            "description": description
        }

    def get_metadata(
        self,
        session_name: str,
        window_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get metadata from session or window.

        Args:
            session_name: Name of tmux session
            window_name: Optional window name (gets session metadata if not provided)

        Returns:
            Dict with metadata
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Target session or window
        if window_name:
            try:
                target = session.windows.get(window_name=window_name)
            except ObjectDoesNotExist:
                return {
                    "status": "error",
                    "message": f"Window '{window_name}' not found"
                }
        else:
            target = session

        # Get metadata (return None if not set)
        metadata = {}
        for key in ["@task_type", "@description", "@created_at", "@created_by"]:
            try:
                value = target.show_option(key, global_=False)
                metadata[key.lstrip("@")] = value
            except:
                metadata[key.lstrip("@")] = None

        return {
            "status": "success",
            "session_name": session_name,
            "window_name": window_name,
            "metadata": metadata
        }

    def _get_log_file_path(self, session_name: str) -> str:
        """Get log file path for session."""
        safe_name = session_name.replace(" ", "_").replace("/", "_")
        return os.path.join(self.log_dir, f"{safe_name}.log")

    def _enable_pipe_pane(self, session_name: str) -> str:
        """Enable pipe-pane logging for session.

        Args:
            session_name: Name of tmux session

        Returns:
            Path to log file
        """
        log_file = self._get_log_file_path(session_name)

        # Enable pipe-pane
        subprocess.run([
            "tmux", "pipe-pane",
            "-t", session_name,
            "-o",  # Append mode
            f"cat >> {log_file}"
        ], check=False)

        # Store log file path in session metadata
        try:
            session = self.server.sessions.get(session_name=session_name)
            session.set_option("@log_file", log_file, global_=False)
        except:
            pass

        return log_file

    def _disable_pipe_pane(self, session_name: str):
        """Disable pipe-pane logging for session."""
        subprocess.run([
            "tmux", "pipe-pane",
            "-t", session_name,
            "-o"  # Toggle off
        ], check=False)

    def _write_command_marker(self, log_file: str, command: str) -> str:
        """Write start marker to log file before command execution.

        Args:
            log_file: Path to log file
            command: Command being executed

        Returns:
            Marker ID (UUID)
        """
        marker_id = uuid.uuid4().hex[:12]
        timestamp = int(time.time())

        marker = f"\n===TERM-AGENT-CMD-START=== {marker_id} {timestamp} {command}\n"

        # Create/append to log file with proper permissions (644)
        try:
            # Open file and write marker
            with open(log_file, "a") as f:
                f.write(marker)

            # Set permissions if file was just created
            if os.path.getsize(log_file) == len(marker):
                os.chmod(log_file, 0o644)
        except PermissionError:
            # Log to stderr but don't fail
            import sys
            print(f"Warning: Could not write to log file {log_file}", file=sys.stderr)

        return marker_id

    def _read_output_from_marker(
        self,
        log_file: str,
        marker_id: str,
        max_lines: int = 20,
        force_full: bool = False
    ) -> Dict[str, Any]:
        """Read output from marker to end, intelligently extracting relevant content.

        Args:
            log_file: Path to log file
            marker_id: Marker ID to search for
            max_lines: Threshold for full vs smart extraction (default 20)

        Returns:
            Dict with output, line_count, and extraction_method
        """
        if not os.path.exists(log_file):
            return {
                "output": [],
                "line_count": 0,
                "extraction_method": "no_file",
                "truncated": False
            }

        # Read entire file
        with open(log_file, "r") as f:
            lines = f.readlines()

        # Find marker
        start_marker = f"===TERM-AGENT-CMD-START=== {marker_id}"
        start_idx = None

        for i, line in enumerate(lines):
            if start_marker in line:
                start_idx = i + 1  # Start after marker line
                break

        if start_idx is None:
            return {
                "output": [],
                "line_count": 0,
                "extraction_method": "marker_not_found",
                "truncated": False
            }

        # Get output from marker to end (or until end marker)
        end_marker = f"===TERM-AGENT-CMD-END=== {marker_id}"
        output_lines = []

        for i in range(start_idx, len(lines)):
            if end_marker in lines[i]:
                break
            # Strip ANSI codes and append
            clean_line = self._strip_ansi_codes(lines[i].rstrip())
            output_lines.append(clean_line)

        line_count = len(output_lines)

        # If forced full or within threshold, return all
        if force_full or line_count <= max_lines:
            return {
                "output": output_lines,
                "line_count": line_count,
                "extraction_method": "full" if force_full else "full",
                "truncated": False,
                "forced_full": force_full
            }

        # Smart extraction for long output
        extracted = self._smart_extract_output(output_lines)

        return {
            "output": extracted["lines"],
            "line_count": line_count,
            "original_line_count": line_count,
            "extraction_method": extracted["method"],
            "truncated": True,
            "message": f"Output has {line_count} lines, showing {len(extracted['lines'])} relevant lines"
        }

    def _strip_ansi_codes(self, text: str) -> str:
        """Strip ANSI escape codes from text.

        Args:
            text: Text with ANSI codes

        Returns:
            Clean text without ANSI codes
        """
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def _smart_extract_output(self, lines: List[str]) -> Dict[str, Any]:
        """Intelligently extract relevant portions of long output.

        Strategy:
        1. Detect error patterns (Python, JS, compilation errors)
        2. For errors: Extract traceback + error context
        3. For success: First 10 + last 10 lines
        4. Remove ANSI codes for cleaner output

        Args:
            lines: All output lines

        Returns:
            Dict with extracted lines and method used
        """
        # Error detection patterns
        error_patterns = [
            (r"Traceback \(most recent call last\)", "python_traceback"),
            (r"Error:", "generic_error"),
            (r"Exception:", "exception"),
            (r"error:", "compilation_error"),
            (r"FAILED", "test_failure"),
            (r"AssertionError", "assertion_error"),
            (r"SyntaxError", "syntax_error"),
            (r"TypeError", "type_error"),
            (r"at .+:\d+:\d+", "javascript_error"),
        ]

        # Check for errors
        error_indices = []
        error_type = None

        for i, line in enumerate(lines):
            for pattern, err_type in error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    error_indices.append(i)
                    if not error_type:
                        error_type = err_type
                    break

        # If errors found, extract context around them
        if error_indices:
            extracted = []
            seen_ranges = set()

            for err_idx in error_indices:
                # Get context: 10 lines before error, error, and up to 20 after
                start = max(0, err_idx - 10)
                end = min(len(lines), err_idx + 20)

                # Avoid duplicate ranges
                range_key = (start, end)
                if range_key not in seen_ranges:
                    seen_ranges.add(range_key)

                    if extracted and extracted[-1] != "...":
                        extracted.append("...")
                        extracted.append("")

                    extracted.extend(lines[start:end])

            # Add last few lines for completion context
            if len(lines) - error_indices[-1] > 20:
                extracted.append("...")
                extracted.append("")
                extracted.extend(lines[-5:])

            return {
                "lines": extracted,
                "method": f"error_extraction_{error_type}"
            }

        # No errors - return first 10 + last 10 with separator
        extracted = []
        extracted.extend(lines[:10])
        extracted.append("")
        extracted.append(f"... ({len(lines) - 20} lines omitted) ...")
        extracted.append("")
        extracted.extend(lines[-10:])

        return {
            "lines": extracted,
            "method": "first_last"
        }

    def list_sessions(self) -> Dict[str, Any]:
        """List all active tmux sessions.

        Returns:
            Dict with list of session names and their info
        """
        sessions = []
        for session in self.server.sessions:
            sessions.append({
                "name": session.name,
                "id": session.id,
                "windows": len(session.windows)
            })

        return {
            "status": "success",
            "sessions": sessions
        }

    def get_or_create_session(
        self,
        session_name: Optional[str] = None,
        task_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing session or create new one.

        Args:
            session_name: Name of session to attach to, or None to create new
            task_type: Type of task (interactive, background, watcher, oneshot)
            description: Human-readable description

        Returns:
            Dict with session info and whether it was created or attached
        """
        action = None

        if session_name:
            # Try to attach to existing
            try:
                session = self.server.sessions.get(session_name=session_name)
                action = "attached"
            except ObjectDoesNotExist:
                # Create with specified name
                session = self.server.new_session(session_name=session_name)
                action = "created"
        else:
            # Generate unique name
            session_name = f"agent-{uuid.uuid4().hex[:8]}"
            session = self.server.new_session(session_name=session_name)
            action = "created"

        # Set metadata if provided and session was created
        if action == "created" and (task_type or description):
            self.set_metadata(session.name, task_type=task_type, description=description)

        return {
            "status": "success",
            "action": action,
            "session_name": session.name,
            "session_id": session.id,
            "windows": len(session.windows),
            "task_type": task_type,
            "description": description
        }

    def execute_command(
        self,
        session_name: str,
        command: str,
        window_name: Optional[str] = None,
        pane_index: int = 0
    ) -> Dict[str, Any]:
        """Execute command in specified session/window/pane.

        Automatically enables pipe-pane logging and inserts marker before command.

        Args:
            session_name: Name of tmux session
            command: Command to execute
            window_name: Optional window name (uses active if not specified)
            pane_index: Index of pane in window (default 0)

        Returns:
            Dict with execution status, marker_id, and log_file
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Enable pipe-pane if not already enabled
        log_file = self._get_log_file_path(session_name)
        if not os.path.exists(log_file):
            self._enable_pipe_pane(session_name)

        # Write marker before command
        marker_id = self._write_command_marker(log_file, command)

        # Store marker in session metadata
        session.set_option("@last_marker", marker_id, global_=False)

        # Get window
        if window_name:
            try:
                window = session.windows.get(window_name=window_name)
            except ObjectDoesNotExist:
                return {
                    "status": "error",
                    "message": f"Window '{window_name}' not found in session '{session_name}'"
                }
        else:
            window = session.active_window

        # Get pane
        if pane_index >= len(window.panes):
            return {
                "status": "error",
                "message": f"Pane index {pane_index} out of range (window has {len(window.panes)} panes)"
            }

        pane = window.panes[pane_index]

        # Send command
        pane.send_keys(command, enter=True)

        return {
            "status": "success",
            "session_name": session_name,
            "window_name": window.name,
            "pane_id": pane.id,
            "marker_id": marker_id,
            "log_file": log_file,
            "message": "Command sent"
        }

    def capture_output(
        self,
        session_name: str,
        window_name: Optional[str] = None,
        pane_index: int = 0,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        use_smart_reading: bool = True
    ) -> Dict[str, Any]:
        """Capture output from specified pane using smart reading from log file.

        If log file exists and smart reading is enabled, reads from log file
        using markers for intelligent extraction. Otherwise falls back to
        capture_pane.

        Args:
            session_name: Name of tmux session
            window_name: Optional window name (uses active if not specified)
            pane_index: Index of pane in window (default 0)
            start_line: Starting line to capture (optional, for capture_pane fallback)
            end_line: Ending line to capture (optional, for capture_pane fallback)
            use_smart_reading: Use smart log reading if available (default True)

        Returns:
            Dict with captured output and metadata
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Try reading from log file first (with or without smart extraction)
        log_file = self._get_log_file_path(session_name)

        if os.path.exists(log_file):
            # Get last marker
            try:
                marker_id = session.show_option("@last_marker", global_=False)

                if marker_id:
                    result = self._read_output_from_marker(
                        log_file,
                        marker_id,
                        force_full=not use_smart_reading
                    )

                    return {
                        "status": "success",
                        "session_name": session_name,
                        "log_file": log_file,
                        "marker_id": marker_id,
                        "output": result["output"],
                        "line_count": result["line_count"],
                        "extraction_method": result["extraction_method"],
                        "truncated": result["truncated"],
                        "forced_full": result.get("forced_full", False),
                        "message": result.get("message")
                    }
            except:
                pass  # Fall through to capture_pane

        # Fallback to capture_pane
        # Get window
        if window_name:
            try:
                window = session.windows.get(window_name=window_name)
            except ObjectDoesNotExist:
                return {
                    "status": "error",
                    "message": f"Window '{window_name}' not found in session '{session_name}'"
                }
        else:
            window = session.active_window

        # Get pane
        if pane_index >= len(window.panes):
            return {
                "status": "error",
                "message": f"Pane index {pane_index} out of range (window has {len(window.panes)} panes)"
            }

        pane = window.panes[pane_index]

        # Capture output (old method)
        output = pane.capture_pane(start=start_line, end=end_line)

        return {
            "status": "success",
            "session_name": session_name,
            "window_name": window.name,
            "pane_id": pane.id,
            "output": output,
            "extraction_method": "capture_pane",
            "truncated": False
        }

    def _is_command_complete(self, output: List[str]) -> bool:
        """Check if command has completed by looking for shell prompt.

        Args:
            output: List of output lines from pane

        Returns:
            True if shell prompt detected in last few lines, False otherwise
        """
        if not output:
            return False

        # Check last 3 lines for common shell prompts
        last_lines = output[-3:]
        prompt_patterns = [
            r'[\$%>#]\s*$',  # Common shell prompts: $, %, >, #
            r'❯\s*$',        # Starship/modern prompts
            r'➜\s*$',        # Oh-my-zsh arrow prompt
            r'~.*[\$%>#]\s*$',  # Prompts with path
        ]

        for line in last_lines:
            for pattern in prompt_patterns:
                if re.search(pattern, line):
                    return True

        return False

    def wait_for_completion(
        self,
        session_name: str,
        timeout: int = 30,
        poll_interval: float = 0.5,
        window_name: Optional[str] = None,
        pane_index: int = 0,
        respect_metadata: bool = True
    ) -> Dict[str, Any]:
        """Wait for command to complete with timeout.

        Polls the pane output looking for shell prompt to return.
        Command continues running in tmux even if timeout occurs.

        Args:
            session_name: Name of tmux session
            timeout: Maximum seconds to wait (default 30)
            poll_interval: Seconds between polls (default 0.5)
            window_name: Optional window name
            pane_index: Index of pane in window
            respect_metadata: If True, check task_type metadata first (default True)

        Returns:
            Dict with completion status, output, and whether it timed out
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Check metadata if requested
        if respect_metadata:
            metadata_result = self.get_metadata(session_name, window_name)
            if metadata_result["status"] == "success":
                task_type = metadata_result["metadata"].get("task_type")

                # Don't wait for background/watcher tasks
                if task_type in ["background", "watcher"]:
                    # Just capture current output and return
                    window = session.active_window if not window_name else session.windows.get(window_name=window_name)
                    pane = window.panes[pane_index]
                    output = pane.capture_pane()

                    return {
                        "status": "running",
                        "session_name": session_name,
                        "window_name": window.name,
                        "pane_id": pane.id,
                        "output": output,
                        "task_type": task_type,
                        "message": f"Task type '{task_type}' - not waiting for completion"
                    }

        # Get window
        if window_name:
            try:
                window = session.windows.get(window_name=window_name)
            except ObjectDoesNotExist:
                return {
                    "status": "error",
                    "message": f"Window '{window_name}' not found in session '{session_name}'"
                }
        else:
            window = session.active_window

        # Get pane
        if pane_index >= len(window.panes):
            return {
                "status": "error",
                "message": f"Pane index {pane_index} out of range"
            }

        pane = window.panes[pane_index]

        # Poll for completion
        start_time = time.time()
        elapsed = 0
        output = []

        while elapsed < timeout:
            output = pane.capture_pane()

            if self._is_command_complete(output):
                return {
                    "status": "completed",
                    "session_name": session_name,
                    "window_name": window.name,
                    "pane_id": pane.id,
                    "output": output,
                    "elapsed_time": round(elapsed, 2),
                    "timed_out": False
                }

            time.sleep(poll_interval)
            elapsed = time.time() - start_time

        # Timeout reached - capture final output
        output = pane.capture_pane()

        return {
            "status": "timeout",
            "session_name": session_name,
            "window_name": window.name,
            "pane_id": pane.id,
            "output": output,
            "elapsed_time": round(elapsed, 2),
            "timed_out": True,
            "message": f"Command still running after {timeout}s (check again later with 'capture' or 'wait')"
        }

    def kill_session(self, session_name: str, keep_log: bool = False) -> Dict[str, Any]:
        """Kill a tmux session and optionally clean up log file.

        Args:
            session_name: Name of session to kill
            keep_log: If False, deletes log file (default False)

        Returns:
            Dict with operation status
        """
        try:
            session = self.server.sessions.get(session_name=session_name)
        except ObjectDoesNotExist:
            return {
                "status": "error",
                "message": f"Session '{session_name}' not found"
            }

        # Disable pipe-pane first
        self._disable_pipe_pane(session_name)

        # Clean up log file unless user wants to keep it
        log_file = self._get_log_file_path(session_name)
        if not keep_log and os.path.exists(log_file):
            try:
                os.remove(log_file)
            except:
                pass  # Don't fail if log cleanup fails

        session.kill()

        return {
            "status": "success",
            "message": f"Session '{session_name}' killed",
            "log_file_removed": not keep_log and os.path.exists(log_file)
        }
