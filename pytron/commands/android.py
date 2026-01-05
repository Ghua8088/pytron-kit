import os
import argparse
from ..platforms.android.ops.init import init_android_project, reset_android_project
from ..platforms.android.ops.sync import sync_android_project
from ..platforms.android.ops.build import build_android_project
from ..platforms.android.ops.run import run_android_project, run_logcat

def cmd_android(args: argparse.Namespace) -> None:
    action = args.action
    project_root = os.getcwd()

    if action == "init":
        # args.force might not be present if not defined in parser, but usually it is for init
        force = getattr(args, "force", False)
        init_android_project(project_root, force=force)
    elif action == "reset":
        reset_android_project(project_root)
    elif action == "sync":
        native = getattr(args, "native", False)
        sync_android_project(project_root, native=native)
    elif action == "build":
        is_aab = getattr(args, "aab", False)
        build_android_project(project_root, is_aab=is_aab)
    elif action == "run":
        run_android_project(project_root)
    elif action == "logcat":
        run_logcat()
