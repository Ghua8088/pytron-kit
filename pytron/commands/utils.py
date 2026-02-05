import json
from pathlib import Path
from typing import Tuple, Dict, Any


def resolve_package_metadata(
    script_path: Path, cli_name: str | None
) -> Tuple[str, Dict[str, Any]]:
    """
    Resolves the output artifact name and loads settings.json.
    Prioritizes CLI name > settings.json title > script stem.
    """
    settings = {}
    out_name = cli_name

    # 1. Load settings.json if exists
    try:
        settings_path = script_path.parent / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
    except Exception:
        # If settings are malformed, we just proceed with empty settings
        pass

    # 2. Resolve Name
    if not out_name:
        # Try metadata title
        title = settings.get("title")
        if title:
            # Sanitize title
            out_name = "".join(
                c if c.isalnum() or c in ("-", "_") else "_" for c in title
            )
            while "__" in out_name:
                out_name = out_name.replace("__", "_")
            out_name = out_name.strip("_")

    if not out_name:
        # Fallback to script stem (e.g. 'app')
        out_name = script_path.stem

    return out_name, settings
