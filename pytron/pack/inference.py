import math
import collections
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple


class SimpleTextClassifier:
    """
    A lightweight Naive Bayes classifier implemented from scratch.
    Predicts Packaging Strategy (Y) based on Code Features (X).
    """

    def __init__(self):
        # Counts: class -> token -> count
        self.feature_counts = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )
        # Counts: class -> total_tokens
        self.class_token_counts = collections.defaultdict(int)
        # Counts: class -> number_of_examples
        self.class_counts = collections.defaultdict(int)
        self.total_examples = 0
        self.vocab = set()

    def train(self, features: List[str], label: str):
        """
        Ingest one training example.
        """
        self.class_counts[label] += 1
        self.total_examples += 1

        for f in features:
            self.feature_counts[label][f] += 1
            self.class_token_counts[label] += 1
            self.vocab.add(f)

    def predict(self, features: List[str]) -> Dict[str, float]:
        """
        Returns probabilities for each class.
        """
        scores = {}
        for label in self.class_counts:
            # P(Class)
            log_prob = math.log(self.class_counts[label] / self.total_examples)

            # P(Feature | Class)
            # Use Laplace Smoothing (add-1)
            denominator = self.class_token_counts[label] + len(self.vocab)

            for f in features:
                # If feature is unknown in training, we ignore it (or count as 0 with smoothing)
                # Naive Bayes assumption: multiply probabilities (add logs)
                count = self.feature_counts[label].get(f, 0) + 1
                log_prob += math.log(count / denominator)

            scores[label] = log_prob

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def save(self, path: Path):
        data = {
            "feature_counts": {k: dict(v) for k, v in self.feature_counts.items()},
            "class_token_counts": dict(self.class_token_counts),
            "class_counts": dict(self.class_counts),
            "total_examples": self.total_examples,
            "vocab": list(self.vocab),
        }
        path.write_text(json.dumps(data))

    def load(self, path: Path):
        data = json.loads(path.read_text())
        self.feature_counts = collections.defaultdict(
            lambda: collections.defaultdict(int),
            {
                k: collections.defaultdict(int, v)
                for k, v in data["feature_counts"].items()
            },
        )
        self.class_token_counts = collections.defaultdict(
            int, data["class_token_counts"]
        )
        self.class_counts = collections.defaultdict(int, data["class_counts"])
        self.total_examples = data["total_examples"]
        self.vocab = set(data["vocab"])


class FeatureExtractor:
    """
    Extracts 'X' (Feature Vector) from Source Code.
    Now enhanced with 'Suspicion Flags' (Option A: Systems Approach).
    """

    def extract(self, source_code: str) -> List[str]:
        features = []

        # 1. Suspicion Flags (Explicit Signals)
        # These are strong indicators of dynamic behavior.
        flags = {
            "has_importlib": ["importlib", "import_module"],
            "has_pkgutil": ["pkgutil", "iter_modules"],
            "has_exec": ["exec(", "eval("],
            "has_sys_path": ["sys.path", ".append"],
            "has_backends": ["backends", "plugins", "drivers"],
            "has_ctypes": ["ctypes", "CDLL", "find_library"],
            "has_dunder_import": ["__import__"],
            "has_loader": ["importlib.util", "SourceFileLoader"],
            "has_data_access": ["open(", "read_text", "pkgutil.get_data"],
        }

        for flag_name, keywords in flags.items():
            # If ANY keyword is found, trigger the flag
            if any(k in source_code for k in keywords):
                features.append(f"FLAG:{flag_name}")

        # 2. Bag of Words (Contextual Signals)
        # Use regex to find significant identifiers
        import re

        tokens = re.findall(r"\b[a-zA-Z_]\w+\b", source_code)

        # Filter common stopwords
        stops = {
            "self",
            "def",
            "class",
            "return",
            "import",
            "from",
            "if",
            "else",
            "None",
            "True",
            "False",
            "try",
            "except",
            "in",
            "is",
            "not",
            "and",
            "or",
            "for",
            "while",
            "with",
            "as",
            "pass",
            "continue",
            "break",
            "raise",
        }

        for t in tokens:
            if len(t) > 3 and t not in stops:
                # We prefix tokens to distinguish from flags
                features.append(f"TOKEN:{t}")

        return features
