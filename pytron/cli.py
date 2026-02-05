"""Simple CLI for Pytron: run, init, package, and frontend build helpers.

This implementation uses only the standard library so there are no extra
dependencies. It provides convenience commands to scaffold a minimal app,
run a Python entrypoint, run `pyinstaller` to package, and run frontend builds
for frontend folders.
"""

from __future__ import annotations

import argparse
from .commands.init import cmd_init
from .commands.run import cmd_run
from .commands.package import cmd_package
from .commands.build import cmd_build_frontend
from .commands.info import cmd_info
from .commands.install import cmd_install
from .commands.uninstall import cmd_uninstall
from .commands.show import cmd_show
from .commands.plugin import cmd_plugin
from .commands.frontend import cmd_frontend
from .commands.login import cmd_login, cmd_logout
from .commands.android import cmd_android
from .commands.engine import cmd_engine
from .commands.doctor import cmd_doctor
from .commands.workflow import cmd_workflow
from .commands.scan import cmd_scan
from .console import log


def build_parser() -> argparse.ArgumentParser:
    # Base parser for shared arguments like --logger
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--logger",
        help="Enable file logging (provide path or defaults to pytron.log)",
        nargs="?",
        const="pytron.log",
    )

    parser = argparse.ArgumentParser(
        prog="pytron", description="Pytron CLI", parents=[base_parser]
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser(
        "init", help="Scaffold a minimal Pytron app", parents=[base_parser]
    )
    p_init.add_argument("target", help="Target directory for scaffold")
    p_init.add_argument(
        "--template",
        default="react",
        help="Frontend template (react, vue, svelte, vanilla, etc.)",
    )
    p_init.add_argument(
        "--provider",
        choices=["npm", "yarn", "pnpm", "bun"],
        default="npm",
        help="JS Package Manager to use for scaffolding (default: npm)",
    )
    p_init.set_defaults(func=cmd_init)

    p_install = sub.add_parser(
        "install",
        help="Install dependencies into project environment",
        parents=[base_parser],
    )
    p_install.add_argument(
        "packages",
        nargs="*",
        help="Packages to install (if empty, installs from requirements.json)",
    )
    p_install.add_argument(
        "--plugin",
        action="store_true",
        help="Install as a plugin instead of a Python dependency",
    )
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser(
        "uninstall",
        help="Uninstall dependencies and remove from requirements.json",
        parents=[base_parser],
    )
    p_uninstall.add_argument("packages", nargs="+", help="Packages to uninstall")
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_show = sub.add_parser(
        "show", help="Show installed packages", parents=[base_parser]
    )
    p_show.set_defaults(func=cmd_show)

    p_login = sub.add_parser(
        "login",
        help="Securely store GitHub credentials for plugin installation",
        parents=[base_parser],
    )
    p_login.set_defaults(func=cmd_login)

    p_logout = sub.add_parser(
        "logout",
        help="Log out from GitHub and remove stored credentials",
        parents=[base_parser],
    )
    p_logout.set_defaults(func=cmd_logout)

    p_doctor = sub.add_parser(
        "doctor", help="Check system dependencies", parents=[base_parser]
    )
    p_doctor.set_defaults(func=cmd_doctor)

    p_scan = sub.add_parser(
        "scan", help="Analyze dependency graph with ML Oracle", parents=[base_parser]
    )
    p_scan.add_argument("target", nargs="?", help="Target directory (default: current)")
    p_scan.add_argument("--json", action="store_true", help="Dump graph to JSON")
    p_scan.add_argument(
        "--html", action="store_true", help="Generate interactive HTML graph"
    )
    p_scan.add_argument(
        "--verbose", action="store_true", help="Show raw uncertainty zones"
    )
    p_scan.set_defaults(func=cmd_scan)

    p_frontend = sub.add_parser(
        "frontend",
        help="Frontend commands proxy (runs '<provider> <args>' in the frontend folder)",
        parents=[base_parser],
    )
    p_frontend.add_argument(
        "--provider",
        choices=["npm", "yarn", "pnpm", "bun"],
        default="npm",
        help="JS Package Manager to use (default: npm)",
    )
    p_frontend.add_argument(
        "npm_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the provider (e.g., install, run dev, test)",
    )
    p_frontend.set_defaults(func=cmd_frontend)

    p_run = sub.add_parser(
        "run", help="Run a Python entrypoint script", parents=[base_parser]
    )
    p_run.add_argument(
        "script", nargs="?", help="Path to Python script to run (default: app.py)"
    )
    p_run.add_argument(
        "--dev",
        action="store_true",
        help="Enable dev mode (hot reload + frontend watch)",
    )
    p_run.add_argument(
        "--no-build",
        action="store_true",
        help="Skip automatic frontend build before running",
    )
    p_run.add_argument("--engine", help="Browser engine to use (native)")
    p_run.add_argument(
        "--chrome", action="store_true", help="Shortcut for --engine chrome"
    )
    p_run.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Extra args to forward to script",
        default=[],
    )
    p_run.set_defaults(func=cmd_run)

    p_pkg = sub.add_parser(
        "package", help="Package app using PyInstaller", parents=[base_parser]
    )
    p_pkg.add_argument(
        "script", nargs="?", help="Python entrypoint to package (default: app.py)"
    )

    # General Options
    grp_general = p_pkg.add_argument_group("General Options")
    grp_general.add_argument("--name", help="Output executable name")
    grp_general.add_argument("--icon", help="Path to app icon (.ico)")
    grp_general.add_argument(
        "--console", action="store_true", help="Show console window (debug mode)"
    )
    grp_general.add_argument(
        "--add-data", nargs="*", help="Additional data to include (format: src;dest)"
    )
    grp_general.add_argument(
        "--installer", action="store_true", help="Build NSIS installer after packaging"
    )
    grp_general.add_argument(
        "--smart-assets",
        action="store_true",
        help="Enable auto-inclusion of smart assets (non-code files).",
    )

    # Engine Options
    grp_engine = p_pkg.add_argument_group("Engine Options")
    grp_engine.add_argument("--engine", help="Browser engine to use (native)")
    grp_engine.add_argument(
        "--chrome", action="store_true", help="Shortcut for --engine chrome"
    )

    # Build Strategy
    grp_build = p_pkg.add_argument_group("Build Strategy")
    grp_build.add_argument(
        "--one-file",
        action="store_true",
        help="Package into a single executable file (default for Nuitka)",
    )
    grp_build.add_argument(
        "--one-dir",
        action="store_true",
        help="Package into a directory (default for PyInstaller, faster build)",
    )
    grp_build.add_argument(
        "--nuitka",
        action="store_true",
        help="Use Nuitka compiler instead of PyInstaller (Advanced, secure)",
    )
    grp_build.add_argument(
        "--bundled",
        action="store_true",
        help="Enable grouping of library modules into app.bundle (Cleaner dist)",
    )
    grp_build.add_argument(
        "--no-shake",
        action="store_true",
        help="Disable post-build optimization (Tree Shaking).",
    )

    # Hook Generation
    grp_hooks = p_pkg.add_argument_group("Hook Generation")
    grp_hooks.add_argument(
        "--collect-all",
        action="store_true",
        help='Generate full "collect_all" hooks (larger builds).',
    )
    grp_hooks.add_argument(
        "--force-hooks",
        action="store_true",
        help="Force generation of hooks using collect_submodules.",
    )

    # Security (Fortress/Rust)
    grp_sec = p_pkg.add_argument_group("Security & Hardening")
    grp_sec.add_argument(
        "--secure",
        action="store_true",
        help="Enable Rust Bootloader (Protects source logic)",
    )
    grp_sec.add_argument(
        "--fortress",
        action="store_true",
        help="Enable Fortress Architecture (Hardened Core + Static Shield)",
    )
    grp_sec.add_argument(
        "--no-cython",
        action="store_true",
        help="Disable Cythonization during Fortress build.",
    )
    grp_sec.add_argument(
        "--patch-from",
        help="Generate a binary patch against a previous app.pytron payload",
    )

    p_pkg.set_defaults(func=cmd_package)

    p_build = sub.add_parser(
        "build-frontend",
        help="Run frontend build in a frontend folder",
        parents=[base_parser],
    )
    p_build.add_argument("folder", help="Frontend folder (contains package.json)")
    p_build.set_defaults(func=cmd_build_frontend)

    p_info = sub.add_parser("info", help="Show environment info", parents=[base_parser])
    p_info.set_defaults(func=cmd_info)

    # Plugin Management
    p_plugin = sub.add_parser(
        "plugin", help="Manage application plugins", parents=[base_parser]
    )
    plugin_sub = p_plugin.add_subparsers(dest="plugin_command")

    # Plugin Install
    p_plugin_inst = plugin_sub.add_parser(
        "install", help="Install a plugin from GitHub"
    )
    p_plugin_inst.add_argument(
        "identifier", help="username.repo.version (e.g. ghua8088.pytron-weather-plugin)"
    )

    # Plugin List
    plugin_sub.add_parser("list", help="List installed plugins")

    # Plugin Create
    p_plugin_create = plugin_sub.add_parser("create", help="Scaffold a new plugin")
    p_plugin_create.add_argument("name", help="Name of the plugin directory")

    # Plugin Uninstall
    p_plugin_uninst = plugin_sub.add_parser("uninstall", help="Remove a plugin")
    p_plugin_uninst.add_argument("name", help="Directory name of the plugin to remove")

    p_plugin.set_defaults(func=cmd_plugin)

    p_android = sub.add_parser(
        "android", help="Android build tools", parents=[base_parser]
    )
    p_android.add_argument(
        "action",
        choices=["init", "sync", "build", "run", "logcat", "reset"],
        help="Action to perform",
    )
    p_android.add_argument(
        "--force", action="store_true", help="Force overwrite during init"
    )
    p_android.add_argument(
        "--native",
        action="store_true",
        help="Enable native extension cross-compilation (defaults to False)",
    )
    p_android.add_argument(
        "--aab",
        action="store_true",
        help="Build Android App Bundle (.aab) for Google Play Store",
    )
    p_android.set_defaults(func=cmd_android)

    p_workflow = sub.add_parser(
        "workflow", help="CI/CD Workflow management", parents=[base_parser]
    )
    p_workflow.set_defaults(func=cmd_workflow)

    # Engine Management
    p_eng = sub.add_parser(
        "engine",
        help="Manage browser engines (Mojo Chrome, etc.)",
        parents=[base_parser],
    )
    eng_sub = p_eng.add_subparsers(dest="engine_command")

    pe_inst = eng_sub.add_parser("install", help="Install/Forge a browser engine")
    pe_inst.add_argument("name", choices=["chrome"], help="Name of the engine")

    p_eng.set_defaults(func=cmd_engine)

    return parser


from .exceptions import PytronError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Initialize logger if requested
    if getattr(args, "logger", None):
        from .console import set_log_file

        set_log_file(args.logger)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled")
        return 1
    except PytronError as e:
        log(str(e), style="error")
        return 1
    except Exception as e:
        import traceback

        traceback.print_exc()
        log(f"Unexpected error: {e}", style="error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
