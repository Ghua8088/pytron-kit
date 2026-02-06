import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from ..console import log, console, get_progress
from ..exceptions import BuildError, ModuleError


@dataclass
class BuildContext:
    # CLI Arguments
    script: Path
    out_name: str
    app_icon: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)

    # Bundle Data
    add_data: List[str] = field(default_factory=list)
    binaries: List[str] = field(default_factory=list)
    hidden_imports: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)
    pathex: List[str] = field(default_factory=list)
    extra_args: List[str] = field(default_factory=list)
    runtime_hooks: List[str] = field(default_factory=list)

    # Path Helpers
    package_dir: Path = field(init=False)
    script_dir: Path = field(init=False)
    build_dir: Path = field(init=False)
    dist_dir: Path = field(init=False)

    # Engine & Security Flags
    engine: Optional[str] = None
    is_secure: bool = False
    is_nuitka: bool = False
    is_onefile: bool = False

    # Internal State
    progress: Any = None
    task_id: Any = None

    def __post_init__(self):
        import pytron

        self.package_dir = Path(pytron.__file__).resolve().parent.parent
        self.script_dir = self.script.parent
        self.build_dir = Path("build")
        self.dist_dir = Path("dist") / self.out_name


class BuildModule:
    """Base class for build modules."""

    def prepare(self, context: BuildContext):
        """Phase 1: Gather assets and requirements."""
        pass

    def build_wrapper(self, context: BuildContext, build_func):
        """Phase 2: Wrap or modify the actual build execution.
        Must return a function or call build_func.
        """
        return build_func(context)

    def post_build(self, context: BuildContext):
        """Phase 3: Cleanup, patching, signing."""
        pass


class Pipeline:
    def __init__(self, context: BuildContext):
        self.context = context
        self.modules: List[BuildModule] = []

    def add_module(self, module: BuildModule):
        self.modules.append(module)

    def run(self, core_build_func):
        """
        Execution flow:
        1. Prepare (All modules)
        2. Build Wrapper (Nested call)
        3. Post Build (All modules, reverse order)
        """
        try:
            # 1. Prepare
            for module in self.modules:
                try:
                    module.prepare(self.context)
                except Exception as e:
                    module_name = module.__class__.__name__
                    raise ModuleError(
                        f"Preparation failed: {e}", module_name=module_name
                    ) from e

            # 2. Build Wrapper (Chain them)
            current_build_func = core_build_func

            # We wrap it in reverse order so the first module added is the outermost wrapper
            for module in reversed(self.modules):
                # Create a closure to capture the current state of build_func
                def make_wrapper(m, func):
                    def wrapped(ctx):
                        try:
                            return m.build_wrapper(ctx, func)
                        except Exception as e:
                            m_name = m.__class__.__name__
                            if isinstance(e, ModuleError):
                                raise
                            raise ModuleError(
                                f"Build step failed: {e}", module_name=m_name
                            ) from e

                    return wrapped

                current_build_func = make_wrapper(module, current_build_func)

            try:
                ret_code = current_build_func(self.context)
            except BuildError:
                raise
            except Exception as e:
                raise BuildError(f"Core build execution failed: {e}") from e

            # 3. Post Build
            if ret_code == 0:
                for module in self.modules:
                    try:
                        module.post_build(self.context)
                    except Exception as e:
                        module_name = module.__class__.__name__
                        log(
                            f"Warning: [{module_name}] post_build failed: {e}",
                            style="warning",
                        )

            return ret_code

        except BuildError as e:
            log(f"Pipeline Error: {e}", style="error")
            if hasattr(e, "__cause__") and e.__cause__:
                log(f"  + Cause: {e.__cause__}", style="dim")
            return 1
        except Exception as e:
            log(f"Unexpected Pipeline Crash: {e}", style="error")
            import traceback

            console.print(traceback.format_exc(), style="dim")
            return 1
