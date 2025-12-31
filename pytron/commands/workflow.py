import argparse
import os
from pathlib import Path
from ..console import log, console, print_rule

WORKFLOW_TEMPLATE = r"""name: Package App (Multi-Platform)

on:
  push:
    tags:
      - 'v*' # Trigger on version tags like v1.0.0
  workflow_dispatch: # Allow manual trigger

jobs:
  package:
    name: Build for ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest, macos-latest]
        python-version: ["3.11"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Linux Dependencies
        if: matrix.os == 'ubuntu-latest'
        run: |
          sudo apt-get update
          sudo apt-get install -y libwebkit2gtk-4.1-0 libgtk-3-dev

      - name: Install Pytron & Dependencies
        run: |
          pip install pytron-kit
          pytron install

      - name: Build and Package
        run: pytron package --smart-assets --installer

      - name: Upload Artifact
        uses: actions/upload-artifact@v4
        with:
          name: pytron-build-${{ matrix.os }}
          path: dist/
"""


def cmd_workflow(args: argparse.Namespace) -> int:
    if args.workflow_command == "init":
        return cmd_workflow_init(args)
    return 0


def cmd_workflow_init(args: argparse.Namespace) -> int:
    print_rule("Pytron Workflow Generator")

    project_root = Path(".").resolve()
    github_dir = project_root / ".github" / "workflows"

    if not github_dir.exists():
        log(f"Creating directory: {github_dir}", style="dim")
        github_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = github_dir / "package.yml"

    if workflow_file.exists() and not getattr(args, "force", False):
        log(f"Workflow file already exists at {workflow_file}", style="warning")
        log("Use --force to overwrite.", style="dim")
        return 1

    log(f"Generating GitHub Action: {workflow_file}", style="info")
    workflow_file.write_text(WORKFLOW_TEMPLATE, encoding="utf-8")

    log("Successfully created multi-platform build workflow!", style="success")
    console.print("\n[bold]Next steps:[/bold]")
    console.print(
        "1. Commit the new file: [cyan]git add .github/workflows/package.yml[/cyan]"
    )
    console.print("2. Tag a version: [cyan]git tag v1.0.0[/cyan]")
    console.print("3. Push to GitHub: [cyan]git push origin main --tags[/cyan]")
    console.print(
        "\nYour app will automatically build for Windows, Linux, and macOS on every tag push!"
    )

    return 0
