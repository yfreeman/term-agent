"""CLI interface for term-agent."""

import json
import sys
import argparse
from typing import Optional
from term_agent.agent import TerminalAgent


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Stateless terminal agent for Claude Code using tmux"
    )

    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # List sessions
    subparsers.add_parser("list", help="List all tmux sessions")

    # Create/attach to session
    create_parser = subparsers.add_parser("create", help="Create or attach to session")
    create_parser.add_argument(
        "--name",
        help="Session name (auto-generated if not provided)"
    )
    create_parser.add_argument(
        "--task-type",
        choices=["interactive", "background", "watcher", "oneshot"],
        help="Type of task (interactive, background, watcher, oneshot)"
    )
    create_parser.add_argument(
        "--description",
        help="Human-readable description of the task"
    )

    # Execute command
    exec_parser = subparsers.add_parser("exec", help="Execute command in session")
    exec_parser.add_argument("session", help="Session name")
    exec_parser.add_argument("command", help="Command to execute")
    exec_parser.add_argument("--window", help="Window name (uses active if not specified)")
    exec_parser.add_argument("--pane", type=int, default=0, help="Pane index (default: 0)")

    # Capture output
    capture_parser = subparsers.add_parser("capture", help="Capture pane output")
    capture_parser.add_argument("session", help="Session name")
    capture_parser.add_argument("--window", help="Window name (uses active if not specified)")
    capture_parser.add_argument("--pane", type=int, default=0, help="Pane index (default: 0)")
    capture_parser.add_argument("--start", type=int, help="Start line")
    capture_parser.add_argument("--end", type=int, help="End line")
    capture_parser.add_argument("--full", action="store_true", help="Return full output without smart extraction")

    # Wait for completion
    wait_parser = subparsers.add_parser("wait", help="Wait for command completion")
    wait_parser.add_argument("session", help="Session name")
    wait_parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds (default: 30)")
    wait_parser.add_argument("--window", help="Window name (uses active if not specified)")
    wait_parser.add_argument("--pane", type=int, default=0, help="Pane index (default: 0)")
    wait_parser.add_argument("--no-respect-metadata", action="store_true", help="Ignore task_type metadata")

    # Metadata management
    metadata_parser = subparsers.add_parser("metadata", help="Get or set session metadata")
    metadata_parser.add_argument("session", help="Session name")
    metadata_parser.add_argument("--window", help="Window name (operates on session if not specified)")
    metadata_parser.add_argument("--get", action="store_true", help="Get metadata (default)")
    metadata_parser.add_argument("--set", action="store_true", help="Set metadata")
    metadata_parser.add_argument("--task-type", choices=["interactive", "background", "watcher", "oneshot"], help="Task type to set")
    metadata_parser.add_argument("--description", help="Description to set")

    # Kill session
    kill_parser = subparsers.add_parser("kill", help="Kill a session")
    kill_parser.add_argument("session", help="Session name")

    # JSON mode for programmatic use
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    # Log directory
    parser.add_argument(
        "--log-dir",
        help="Directory for log files (default: auto-detect or ~/.term-agent/logs)"
    )

    # Parse arguments
    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    # Create agent
    agent = TerminalAgent(log_dir=args.log_dir if hasattr(args, 'log_dir') else None)

    # Execute action
    result = None

    if args.action == "list":
        result = agent.list_sessions()

    elif args.action == "create":
        result = agent.get_or_create_session(
            args.name,
            task_type=getattr(args, 'task_type', None),
            description=getattr(args, 'description', None)
        )

    elif args.action == "exec":
        result = agent.execute_command(
            args.session,
            args.command,
            window_name=args.window,
            pane_index=args.pane
        )

    elif args.action == "capture":
        result = agent.capture_output(
            args.session,
            window_name=args.window,
            pane_index=args.pane,
            start_line=args.start,
            end_line=args.end,
            use_smart_reading=not args.full
        )

    elif args.action == "wait":
        result = agent.wait_for_completion(
            args.session,
            timeout=args.timeout,
            window_name=args.window,
            pane_index=args.pane,
            respect_metadata=not args.no_respect_metadata
        )

    elif args.action == "metadata":
        if args.set or args.task_type or args.description:
            # Set metadata
            result = agent.set_metadata(
                args.session,
                task_type=args.task_type,
                description=args.description,
                window_name=args.window
            )
        else:
            # Get metadata (default)
            result = agent.get_metadata(
                args.session,
                window_name=args.window
            )

    elif args.action == "kill":
        result = agent.kill_session(args.session)

    # Output result
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        if result["status"] == "error":
            print(f"Error: {result['message']}", file=sys.stderr)
            sys.exit(1)

        if args.action == "list":
            print("Active tmux sessions:")
            for session in result["sessions"]:
                print(f"  {session['name']} ({session['windows']} windows)")

        elif args.action == "create":
            print(f"{result['action'].capitalize()} session: {result['session_name']}")
            print(f"  Attach with: tmux attach -t {result['session_name']}")

        elif args.action == "exec":
            print(f"Command sent to {result['session_name']}")

        elif args.action == "capture":
            print(result["output"])

        elif args.action == "wait":
            status = result["status"]
            if status == "completed":
                print(f"✓ Command completed in {result['elapsed_time']}s")
                print("\nOutput:")
                print(result["output"])
            elif status == "timeout":
                print(f"⏱ Command still running after {result['elapsed_time']}s")
                print("\nCurrent output:")
                print(result["output"])
                print(f"\n{result['message']}")
            elif status == "running":
                print(f"ℹ {result['message']}")
                print("\nCurrent output:")
                print(result["output"])

        elif args.action == "metadata":
            if "metadata" in result:
                # Get metadata
                meta = result["metadata"]
                print(f"Session: {result['session_name']}")
                if result.get("window_name"):
                    print(f"Window: {result['window_name']}")
                print("\nMetadata:")
                for key, value in meta.items():
                    if value:
                        print(f"  {key}: {value}")
            else:
                # Set metadata
                print(result["message"])

        elif args.action == "kill":
            print(result["message"])


if __name__ == "__main__":
    main()
