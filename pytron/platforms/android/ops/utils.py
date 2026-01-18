from rich.markup import escape
from ....console import console, run_command_with_output


def run_command(cmd, cwd=None, env=None):
    # Use markup=False to avoid issues with square brackets in paths
    console.print(f"[{cwd or '.'}] $ {' '.join(cmd)}", style="dim", markup=False)
    return run_command_with_output(cmd, cwd=cwd, env=env, style="dim", shell=False)
