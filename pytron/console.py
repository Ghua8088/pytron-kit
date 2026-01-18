from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.console import Console
from rich.theme import Theme
import subprocess
import os
import datetime

# Export Rule so commands can use it directly
__all__ = [
    "console",
    "log",
    "get_progress",
    "print_rule",
    "run_command_with_output",
    "Rule",
    "set_log_file",
]

# Centralized Theme Definition
# 'dim' is built-in but can be overridden if needed
custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "dim": "dim white",
    }
)

console = Console(theme=custom_theme)
_log_file = None


def set_log_file(path: str | None):
    """Sets the file path for logging."""
    global _log_file
    if path:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    _log_file = path


def log(
    msg: str, style: str = "info", title: str = "Pytron", markup: bool = True
) -> None:
    """Helper to print [Pytron] messages with style and log to file."""
    # Print to console
    try:
        # The title part is always markup (bold)
        console.print(f"[bold][{title}][/bold] ", style=style, end="")
        # The message part can optionally contain Rich markup (e.g. [bold green]...)
        console.print(msg, style=style, markup=markup)
    except Exception:
        # Fallback to plain print if the style or markup is invalid
        print(f"[{title}] {msg}")

    # Log to file if enabled
    if _log_file:
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(_log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{title}] [{style.upper()}] {msg}\n")
        except Exception:
            pass  # Silently fail file logging if it fails


def get_progress() -> Progress:
    """Returns a configured Progress instance for consistent look.
    Transient=True ensures the bar is removed from console after completion.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )


def print_rule(title: str, style: str = "bold cyan") -> None:
    console.print(Rule(f"[{style}]{title}"))


def run_command_with_output(
    cmd, env=None, cwd=None, style="dim", title=None, shell=False
):
    """Runs a command and streams output to the console, compatible with concurrent Progress display."""
    try:
        if title:
            log(title, style="info")

        # Use Popen to capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            cwd=cwd,
            env=env,
            bufsize=1,  # Line buffered
            shell=shell,
        )  # nosec B602

        for line in process.stdout:
            # Strip only trailing newline to preserve some formatting (or strip both?)
            # Usually output has \n at end, print() adds another.
            stripped = line.rstrip()
            if stripped:
                # Printing to console while Progress is active automatically handles "moving" the output above the bar
                console.print(stripped, style=style, markup=False)
                # Also log to file if enabled (without rich tags)
                if _log_file:
                    try:
                        with open(_log_file, "a", encoding="utf-8") as f:
                            f.write(f"  {stripped}\n")
                    except Exception:
                        pass

        process.wait()
        return process.returncode
    except Exception as e:
        console.print("Error running command:", style="error", end=" ")
        console.print(str(e), style="error", markup=False)
        return 1
