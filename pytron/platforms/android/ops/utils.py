from rich.markup import escape
from ....console import console, run_command_with_output


def run_command(cmd, cwd=None, env=None):
    console.print(f"[dim][{escape(str(cwd or '.'))}] $ {escape(' '.join(cmd))}[/dim]")
    return run_command_with_output(cmd, cwd=cwd, env=env, style="dim", shell=False)
