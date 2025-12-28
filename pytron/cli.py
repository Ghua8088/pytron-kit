"""Simple CLI for Pytron: run, init, package, and frontend build helpers.

This implementation uses only the standard library so there are no extra
dependencies. It provides convenience commands to scaffold a minimal app,
run a Python entrypoint, run `pyinstaller` to package, and run `npm run build`
for frontend folders.
"""
from __future__ import annotations

import argparse
import sys
import re
from .commands.init import cmd_init
from .commands.run import cmd_run
from .commands.package import cmd_package
from .commands.build import cmd_build_frontend
from .commands.info import cmd_info
from .commands.install import cmd_install
from .commands.uninstall import cmd_uninstall
from .commands.show import cmd_show
from .commands.frontend import cmd_frontend_install
from .commands.android import cmd_android
from .commands.doctor import cmd_doctor
from .commands.workflow import cmd_workflow
from .console import log, set_log_file


def build_parser() -> argparse.ArgumentParser:
    # Base parser for shared arguments like --logger
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('--logger', help='Enable file logging (provide path or defaults to pytron.log)', nargs='?', const='pytron.log')

    parser = argparse.ArgumentParser(prog='pytron', description='Pytron CLI', parents=[base_parser])
    sub = parser.add_subparsers(dest='command')

    p_init = sub.add_parser('init', help='Scaffold a minimal Pytron app', parents=[base_parser])
    p_init.add_argument('target', help='Target directory for scaffold')
    p_init.add_argument('--template', default='react', help='Frontend template (react, vue, svelte, vanilla, etc.)')
    p_init.set_defaults(func=cmd_init)

    p_install = sub.add_parser('install', help='Install dependencies into project environment', parents=[base_parser])
    p_install.add_argument('packages', nargs='*', help='Packages to install (if empty, installs from requirements.json)')
    p_install.set_defaults(func=cmd_install)
    
    p_uninstall = sub.add_parser('uninstall', help='Uninstall dependencies and remove from requirements.json', parents=[base_parser])
    p_uninstall.add_argument('packages', nargs='+', help='Packages to uninstall')
    p_uninstall.set_defaults(func=cmd_uninstall)
    
    p_show = sub.add_parser('show', help='Show installed packages', parents=[base_parser])
    p_show.set_defaults(func=cmd_show)

    p_doctor = sub.add_parser('doctor', help='Check system for Pytron dependencies', parents=[base_parser])
    p_doctor.set_defaults(func=cmd_doctor)
    
    p_frontend = sub.add_parser('frontend', help='Frontend package management', parents=[base_parser])
    frontend_sub = p_frontend.add_subparsers(dest='frontend_command')
    
    pf_install = frontend_sub.add_parser('install', help='Install packages into the frontend', parents=[base_parser])
    pf_install.add_argument('packages', nargs='*', help='npm packages to install')
    pf_install.set_defaults(func=cmd_frontend_install)

    p_run = sub.add_parser('run', help='Run a Python entrypoint script', parents=[base_parser])
    p_run.add_argument('script', nargs='?', help='Path to Python script to run (default: app.py)')
    p_run.add_argument('--dev', action='store_true', help='Enable dev mode (hot reload + frontend watch)')
    p_run.add_argument('--no-build', action='store_true', help='Skip automatic frontend build before running')
    p_run.add_argument('--engine', help='Browser engine to use (native, pyside6)')
    p_run.add_argument('extra_args', nargs=argparse.REMAINDER, help='Extra args to forward to script', default=[])
    p_run.add_argument('--pyside6', action='store_true', help='Use PySide6 engine')
    p_run.set_defaults(func=cmd_run)

    p_pkg = sub.add_parser('package', help='Package app using PyInstaller', parents=[base_parser])
    p_pkg.add_argument('script', nargs='?', help='Python entrypoint to package (default: app.py)')
    p_pkg.add_argument('--name', help='Output executable name')
    p_pkg.add_argument('--icon', help='Path to app icon (.ico)')
    p_pkg.add_argument('--noconsole', action='store_true', help='Hide console window')
    p_pkg.add_argument('--add-data', nargs='*', help='Additional data to include (format: src;dest)')
    p_pkg.add_argument('--installer', action='store_true', help='Build NSIS installer after packaging')
    p_pkg.add_argument('--collect-all', action='store_true', help='Generate full "collect_all" hooks (larger builds).')
    p_pkg.add_argument('--force-hooks', action='store_true', help='Force generation of hooks using collect_submodules (smaller hooks).')
    p_pkg.add_argument('--smart-assets', action='store_true', help='Enable auto-inclusion of smart assets (non-code files).')
    p_pkg.add_argument('--pyside6', action='store_true', help='Use PySide6 engine')
    p_pkg.add_argument('--engine', help='Browser engine to use (native, pyside6)')
    p_pkg.set_defaults(func=cmd_package)
    p_build = sub.add_parser('build-frontend', help='Run npm build in a frontend folder', parents=[base_parser])
    p_build.add_argument('folder', help='Frontend folder (contains package.json)')
    p_build.set_defaults(func=cmd_build_frontend)

    p_info = sub.add_parser('info', help='Show environment info', parents=[base_parser])
    p_info.set_defaults(func=cmd_info)

    p_android = sub.add_parser('android', help='Android build tools', parents=[base_parser])
    p_android.add_argument('action', choices=['init', 'sync', 'build', 'run', 'logcat', 'reset'], help='Action to perform')
    p_android.add_argument('--force', action='store_true', help='Force overwrite during init')
    p_android.add_argument('--native', action='store_true', help='Enable native extension cross-compilation (defaults to False)')
    p_android.add_argument('--aab', action='store_true', help='Build Android App Bundle (.aab) for Google Play Store')
    p_android.set_defaults(func=cmd_android)

    p_workflow = sub.add_parser('workflow', help='CI/CD Workflow management', parents=[base_parser])
    workflow_sub = p_workflow.add_subparsers(dest='workflow_command')
    
    pw_init = workflow_sub.add_parser('init', help='Initialize GitHub Actions for multi-platform packaging', parents=[base_parser])
    pw_init.add_argument('--force', action='store_true', help='Overwrite existing workflow file')
    pw_init.set_defaults(func=cmd_workflow)

    return parser


from .exceptions import PytronError

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    
    # Initialize logger if requested
    if getattr(args, 'logger', None):
        from .console import set_log_file
        set_log_file(args.logger)
    
    if not hasattr(args, 'func'):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print('\nCancelled')
        return 1
    except PytronError as e:
        log(str(e), style="error")
        return 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"Unexpected error: {e}", style="error")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
