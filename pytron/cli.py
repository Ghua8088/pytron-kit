"""Simple CLI for Pytron: run, init, package, and frontend build helpers.

This implementation uses only the standard library so there are no extra
dependencies. It provides convenience commands to scaffold a minimal app,
run a Python entrypoint, run `pyinstaller` to package, and run `npm run build`
for frontend folders.
"""
from __future__ import annotations

import argparse
import sys

from .commands.init import cmd_init
from .commands.run import cmd_run
from .commands.package import cmd_package
from .commands.build import cmd_build_frontend
from .commands.info import cmd_info
from .commands.install import cmd_install


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='pytron', description='Pytron CLI')
    sub = parser.add_subparsers(dest='command')

    p_init = sub.add_parser('init', help='Scaffold a minimal Pytron app')
    p_init.add_argument('target', help='Target directory for scaffold')
    p_init.add_argument('--template', default='react', help='Frontend template (react, vue, svelte, vanilla, etc.)')
    p_init.set_defaults(func=cmd_init)

    p_install = sub.add_parser('install', help='Install dependencies into project environment')
    p_install.add_argument('packages', nargs='*', help='Packages to install (if empty, installs from requirements.json)')
    p_install.set_defaults(func=cmd_install)

    p_run = sub.add_parser('run', help='Run a Python entrypoint script')
    p_run.add_argument('script', nargs='?', help='Path to Python script to run (default: app.py)')
    p_run.add_argument('--dev', action='store_true', help='Enable dev mode (hot reload + frontend watch)')
    p_run.add_argument('--no-build', action='store_true', help='Skip automatic frontend build before running')
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER, help='Extra args to forward to script', default=[])
    p_run.set_defaults(func=cmd_run)

    p_pkg = sub.add_parser('package', help='Package app using PyInstaller')
    p_pkg.add_argument('script', nargs='?', help='Python entrypoint to package (default: app.py)')
    p_pkg.add_argument('--name', help='Output executable name')
    p_pkg.add_argument('--icon', help='Path to app icon (.ico)')
    p_pkg.add_argument('--noconsole', action='store_true', help='Hide console window')
    p_pkg.add_argument('--add-data', nargs='*', help='Additional data to include (format: src;dest)')
    p_pkg.add_argument('--installer', action='store_true', help='Build NSIS installer after packaging')
    p_pkg.add_argument('--collect-all', action='store_true', help='Generate full "collect_all" hooks (larger builds).')
    p_pkg.add_argument('--force-hooks', action='store_true', help='Force generation of hooks using collect_submodules (smaller hooks).')
    p_pkg.add_argument('--smart-assets', action='store_true', help='Enable auto-inclusion of smart assets (non-code files).')
    p_pkg.set_defaults(func=cmd_package)

    p_build = sub.add_parser('build-frontend', help='Run npm build in a frontend folder')
    p_build.add_argument('folder', help='Frontend folder (contains package.json)')
    p_build.set_defaults(func=cmd_build_frontend)

    p_info = sub.add_parser('info', help='Show environment info')
    p_info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, 'func'):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print('\nCancelled')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
