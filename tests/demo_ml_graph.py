from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from pytron.pack.graph import GraphBuilder, DependencyOracle
from pytron.console import log


def main():
    root = Path(r"d:\playground\pytron\pytron")
    log(f"Scanning project root: {root}", style="info")

    # 1. Build the Static Fact Graph
    builder = GraphBuilder(root)

    # --- SIMULATION INJECTION ---
    # 1. Known Package (Pandas) -> Triggers KB Lookup
    sim_node = builder.graph.add_node("user_app", Path("user_app.py"))
    sim_node.literals.add("pandas")
    builder.graph.mark_uncertainty(
        "user_app", 10, "import_module('pandas')", "dynamic_import"
    )

    pandas_node = builder.graph.add_node(
        "pandas", Path("site-packages/pandas/__init__.py")
    )
    builder.graph.mark_uncertainty("pandas", 1, "lazy_loader", "dynamic_import")

    # 2. Unseen Package (Custom Plugin Lib) -> Triggers ML Model
    # We create a fake file with "plugin-like" source code features
    unseen_path = root.parent / "my_custom_lib" / "__init__.py"
    unseen_path.parent.mkdir(parents=True, exist_ok=True)
    unseen_path.write_text(
        """
    import importlib
    import os
    
    def load_plugins():
        # This code looks like it collects submodules
        for f in os.listdir(os.path.dirname(__file__)):
             if f.endswith(".py"):
                 importlib.import_module(f)
    """,
        encoding="utf-8",
    )

    unseen_node = builder.graph.add_node("my_custom_lib", unseen_path)
    builder.graph.mark_uncertainty(
        "my_custom_lib", 5, "importlib.import_module", "dynamic_import"
    )

    # 3. Simulate a "Mini Django" (Titan Pattern)
    # Django uses 'import_module' inside a 'management/commands' loops.
    # Our model learned this from the real Django.
    titan_path = root.parent / "mini_django" / "management" / "__init__.py"
    titan_path.parent.mkdir(parents=True, exist_ok=True)
    titan_path.write_text(
        """
    from importlib import import_module
    import pkgutil
    
    def load_commands():
        # Iterate over modules
        for _, name, _ in pkgutil.iter_modules(__path__):
            import_module(name)
    """,
        encoding="utf-8",
    )

    titan_node = builder.graph.add_node("mini_django", titan_path)
    # The flag 'pkgutil' and 'import_module' together strongly correlate with COLLECT_SUBMODULES
    builder.graph.mark_uncertainty(
        "mini_django", 5, "pkgutil.iter_modules", "dynamic_import"
    )

    # Resume normal scan
    graph = builder.scan_project()

    log(
        f"Static Phase Complete: Found {len(graph.nodes)} nodes and {len(graph.edges)} static edges.",
        style="dim",
    )
    log(f"Uncertainty Zones Detected: {len(graph._uncertainty_zones)}", style="warning")

    # 2. Run the Oracle (ML Prediction)
    log("Running ML Dependency Oracle...", style="cyan")
    oracle = DependencyOracle(graph)
    oracle.predict()

    # 3. Show Results
    print("\n--- ML PREDICTIONS ---")
    predicted_edges = [e for e in graph.edges if e.type == "predicted"]

    if not predicted_edges:
        print("No high-confidence predictions found.")
    else:
        for e in predicted_edges:
            color = "green" if e.confidence > 0.8 else "yellow"
            print(
                f"[{color}] {e.source} -> {e.target} (Conf: {e.confidence}) | Reason: {e.reason}"
            )

    # 4. Dump JSON (The format you asked for)
    print("\n--- JSON OUTPUT SAMPLE ---")
    json_out = graph.to_json()
    # Print just a snippet
    print(json_out[:500] + "...")

    # Save it
    Path("graph_output.json").write_text(json_out)
    log("\nFull graph saved to 'graph_output.json'", style="dim")


if __name__ == "__main__":
    main()
