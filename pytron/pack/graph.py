from __future__ import annotations
import ast
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any


@dataclass
class Edge:
    source: str
    target: str
    type: str  # "static", "dynamic", "side-effect"
    confidence: float  # 0.0 to 1.0
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Node:
    name: str  # fully qualified module name
    path: Optional[Path] = None
    type: str = "module"  # "module", "package", "resource"
    features: Set[str] = field(
        default_factory=set
    )  # extracted signals (e.g. "has_getattr")
    literals: Set[str] = field(
        default_factory=set
    )  # interesting string literals found in source

    def to_dict(self):
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "type": self.type,
            "features": list(self.features),
            "literals": list(self.literals),
        }


class SideEffectGraph:
    """
    A probabilistic dependency graph that models the uncertainty of Python imports.
    """

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._uncertainty_zones: List[Dict] = []  # Places where dynamic magic happens

    def add_node(self, name: str, path: Path = None) -> Node:
        if name not in self.nodes:
            self.nodes[name] = Node(name=name, path=path)
        return self.nodes[name]

    def add_edge(
        self,
        source: str,
        target: str,
        type: str,
        confidence: float = 1.0,
        reason: str = "",
    ):
        # Avoid duplicates
        for e in self.edges:
            if e.source == source and e.target == target and e.type == type:
                return

        self.edges.append(Edge(source, target, type, confidence, reason))

    def mark_uncertainty(
        self, source_node: str, line_no: int, code_snippet: str, heuristic: str
    ):
        """
        Registers a 'Known Unknown'. This is a task for the ML Oracle.
        """
        self._uncertainty_zones.append(
            {
                "source": source_node,
                "line": line_no,
                "code": code_snippet,
                "heuristic": heuristic,
                "resolved": False,
            }
        )

    def to_json(self) -> str:
        data = {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [
                {
                    "from": e.source,
                    "to": e.target,
                    "type": e.type,
                    "confidence": e.confidence,
                    "reason": e.reason,
                }
                for e in self.edges
            ],
            "uncertainty": self._uncertainty_zones,
        }
        return json.dumps(data, indent=2)


class GraphBuilder:
    """
    Static Analyzer that populates the SideEffectGraph.
    """

    def __init__(self, root: Path):
        self.root = root
        self.graph = SideEffectGraph()

    def scan_project(self):
        """Scans all .py files in the root recursively."""
        for path in self.root.rglob("*.py"):
            self._analyze_file(path)
        return self.graph

    def _analyze_file(self, path: Path):
        # Convert path to module name
        try:
            rel_path = path.relative_to(self.root)
            module_name = ".".join(rel_path.with_suffix("").parts)
        except ValueError:
            module_name = path.name

        node = self.graph.add_node(module_name, path)

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            self._visit_node(node, tree)
        except Exception:
            pass

    def _visit_node(self, node: Node, tree: ast.AST):
        """
        Extracts features and static edges from AST.
        """
        for s in ast.walk(tree):
            # 1. Static Imports (Confidence 1.0)
            if isinstance(s, ast.Import):
                for alias in s.names:
                    self.graph.add_edge(
                        node.name, alias.name, "static", 1.0, "import_stmt"
                    )

            elif isinstance(s, ast.ImportFrom):
                if s.module:
                    self.graph.add_edge(
                        node.name, s.module, "static", 1.0, "from_import_stmt"
                    )

            # 2. String Literals (Feature Extraction for ML)
            elif isinstance(s, ast.Constant) and isinstance(s.value, str):
                # Heuristic: Only keep "interesting" strings (no whitespace, len > 3)
                txt = s.value.strip()
                if len(txt) > 3 and " " not in txt:
                    node.literals.add(txt)

            # 3. Dynamic Triggers (The Uncertainty)
            elif isinstance(s, ast.Call):
                if isinstance(s.func, ast.Attribute):
                    # importlib.import_module(...)
                    if s.func.attr == "import_module":
                        node.features.add("calls_import_module")
                        self.graph.mark_uncertainty(
                            node.name,
                            getattr(s, "lineno", 0),
                            "import_module",
                            "dynamic_import",
                        )
                elif isinstance(s.func, ast.Name):
                    # __import__(...)
                    if s.func.id == "__import__":
                        node.features.add("calls_dunder_import")
                        self.graph.mark_uncertainty(
                            node.name,
                            getattr(s, "lineno", 0),
                            "__import__",
                            "dynamic_import",
                        )


from .inference import SimpleTextClassifier, FeatureExtractor


class DependencyOracle:
    """
    The 'Bridge' between the Graph and the ML Model.
    Now powered by the 'Oracle of Hooks' dataset mined from ecosystem history.
    """

    def __init__(self, graph: SideEffectGraph):
        self.graph = graph
        self.knowledge_base = self._load_knowledge_base()
        self.classifier = self._load_model()
        self.extractor = FeatureExtractor()

    def _load_model(self):
        try:
            # Look for the brain in the sibling directory
            # structure: d:/playground/pytron/pytron/pack/graph.py
            # target:    d:/playground/brain/model.json

            # Robust logic: find the project root and go up one
            current = Path(__file__)
            # Go up until we hit 'pytron' repo root
            root = current.parent.parent.parent.parent  # d:/playground
            path = root / "brain" / "model.json"

            if path.exists():
                clf = SimpleTextClassifier()
                clf.load(path)
                return clf
        except Exception:
            pass
        return None

    def _load_knowledge_base(self) -> Dict:
        """Loads the mined signal data (the 'Brain')."""
        try:
            # Look for data.json in the sibling brain directory
            current = Path(__file__)
            root = current.parent.parent.parent.parent
            path = root / "brain" / "data.json"

            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def predict(self):
        """
        Iterates over uncertainty zones and uses the Knowledge Base to predict edges.
        """
        if not self.knowledge_base:
            # Fallback to hardcoded heuristics if KB is missing
            self._predict_heuristic()
            return

        for zone in self.graph._uncertainty_zones:
            source_name = zone["source"]
            node = self.graph.nodes.get(source_name)
            if not node:
                continue

            # --- PREDICTION LOGIC ---
            # 1. Identify the Package Context of the Node
            # e.g., "pandas.core.internals" -> "pandas"
            root_package = source_name.split(".")[0]

            # Check if we have wisdom about this package
            if root_package in self.knowledge_base:
                self._apply_known_wisdom(
                    source_name,
                    root_package,
                    self.knowledge_base[root_package]["signal"],
                )
            else:
                # UNSEEN MODULE DETECTED!
                # Activate "The Generalist" (Zero-Shot Prediction)
                self._predict_unseen_module(zone, node)

            # 2. Cross-Reference Literals (The "Data Bridge")
            # If the code mentions a package string that we know is a heavy dependency
            for literal in node.literals:
                # Naive check: is the literal a known package in our KB?
                if literal in self.knowledge_base and literal != root_package:
                    self.graph.add_edge(
                        source=source_name,
                        target=literal,
                        type="predicted",
                        confidence=0.60,  # Lower confidence for string matching
                        reason=f"oracle_literal_match:{literal}",
                    )

            zone["resolved"] = True

    def _apply_known_wisdom(self, source_name, root_package, signal):
        """Applies expert rules from the Knowledge Base."""
        # Apply Hidden Imports
        for hidden in signal.get("hiddenimports", []):
            if isinstance(hidden, str):
                self.graph.add_edge(
                    source=source_name,
                    target=hidden,
                    type="predicted",
                    confidence=0.95,
                    reason=f"oracle_hook_knowledge_base[{root_package}]",
                )

        # Apply Utility Semantics
        for util in signal.get("utilities", []):
            func = util.get("function")
            if func == "collect_submodules":
                target_arg = util["arguments"][0] if util["arguments"] else root_package
                if isinstance(target_arg, str):
                    self.graph.add_edge(
                        source=source_name,
                        target=f"{target_arg}.*",
                        type="predicted",
                        confidence=0.90,
                        reason="oracle_utility_signal:collect_submodules",
                    )

    def _predict_unseen_module(self, zone, node):
        """
        The Generalist: Zero-Shot prediction for unseen modules.
        Uses the trained Naive Bayes model to classify the module's behavior.
        """
        if not self.classifier:
            # Fallback if model not loaded
            return

        source_name = zone["source"]

        # 1. Get Code Content (X)
        # We need the source code to extract features.
        # If the node.path is a file, read it.
        source_code = ""
        if node.path and node.path.exists():
            try:
                source_code = node.path.read_text(errors="ignore")
            except:
                pass

        if not source_code:
            return

        # 2. Extract Features
        features = self.extractor.extract(source_code)

        # 3. Predict Strategy (Y)
        predictions = self.classifier.predict(features)
        # predictions is list of (label, log_score).
        # Since scores are log-probs, they are negative. Closer to 0 is better.
        # We just take the top one.

        if not predictions:
            return

        best_label, best_score = predictions[0]

        # Thresholding logic for Log Probs is tricky.
        # Simple relative check: is the best score significantly better than the next?
        # Or just trust the rankings.

        # Heuristic validation of the prediction
        reason = f"ml_naive_bayes:{best_label}"

        if best_label == "COLLECT_SUBMODULES":
            # Constraint: Does it look like a package? (Has __path__ or is __init__)
            if node.path.name == "__init__.py":
                self.graph.add_edge(
                    source_name, f"{source_name}.*", "predicted", 0.82, reason
                )

        elif best_label == "COLLECT_DATA":
            # Constraint: Does the directory contain non-py files?
            # Simple check: if we predicted DATA, we imply we need to scan usage.
            # We add a generic data-dependency edge
            self.graph.add_edge(
                source_name, "<resource_data>", "predicted", 0.75, reason
            )

        elif best_label == "HIDDEN_IMPORTS":
            # This suggests specific imports are hidden.
            # Hard to predict WHICH ones without a sequence model.
            # But we can flag it for deeper inspection or scan literals harder.
            pass

    def _predict_heuristic(self):
        """Fallback for when no KB is available (Generic Patterns only)"""
        pass
