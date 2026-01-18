import pytest
import datetime
import uuid
import decimal
import pathlib
import enum
import dataclasses
from pytron.serializer import pytron_serialize, PytronJSONEncoder

# Optional dependencies
try:
    import pydantic

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class TestSerializer:
    def test_primitives(self):
        assert pytron_serialize(1) == 1
        assert pytron_serialize(1.5) == 1.5
        assert pytron_serialize("test") == "test"
        assert pytron_serialize(True) is True
        assert pytron_serialize(None) is None

    def test_standard_types(self):
        # Bytes
        assert pytron_serialize(b"hello") == "aGVsbG8="

        # Datetime
        dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
        assert pytron_serialize(dt) == "2023-01-01T12:00:00"

        # UUID
        uid = uuid.uuid4()
        assert pytron_serialize(uid) == str(uid)

        # Decimal
        dec = decimal.Decimal("10.5")
        assert pytron_serialize(dec) == 10.5

        # Path
        p = pathlib.Path("/tmp/test")
        # Path serialization depends on OS separator, so we check string representation
        assert pytron_serialize(p) == str(p)

        # Set
        s = {1, 2, 3}
        serialized_s = pytron_serialize(s)
        assert isinstance(serialized_s, list)
        assert set(serialized_s) == s

        # Complex
        c = 1 + 2j
        assert pytron_serialize(c) == {"real": 1.0, "imag": 2.0}

    def test_enum(self):
        class Color(enum.Enum):
            RED = 1
            GREEN = 2

        assert pytron_serialize(Color.RED) == 1

    def test_dataclass(self):
        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        p = Point(10, 20)
        assert pytron_serialize(p) == {"x": 10, "y": 20}

    def test_object_dict(self):
        class Person:
            def __init__(self, name, age):
                self.name = name
                self.age = age

        p = Person("Alice", 30)
        assert pytron_serialize(p) == {"name": "Alice", "age": 30}

    def test_object_slots(self):
        class SlottedPoint:
            __slots__ = ["x", "y"]

            def __init__(self, x, y):
                self.x = x
                self.y = y

        p = SlottedPoint(5, 5)
        assert pytron_serialize(p) == {"x": 5, "y": 5}

    @pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not installed")
    def test_pydantic(self):
        class User(pydantic.BaseModel):
            name: str
            id: int

        u = User(name="Bob", id=1)
        assert pytron_serialize(u) == {"name": "Bob", "id": 1}

    @pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")
    def test_pil_image(self):
        # Create a small image
        img = Image.new("RGB", (10, 10), color="red")
        serialized = pytron_serialize(img)
        assert serialized.startswith("data:image/png;base64,")

    def test_nested_structures(self):
        data = {
            "list": [1, 2, {"a": 3}],
            "dict": {"b": [4, 5], "c": {"d": 6}},
            "mixed": [
                datetime.datetime(2023, 1, 1),
                uuid.UUID("12345678-1234-5678-1234-567812345678"),
                decimal.Decimal("1.23"),
            ],
        }
        serialized = pytron_serialize(data)
        assert serialized["list"][2]["a"] == 3
        assert serialized["dict"]["c"]["d"] == 6
        assert serialized["mixed"][0] == "2023-01-01T00:00:00"
        assert serialized["mixed"][1] == "12345678-1234-5678-1234-567812345678"
        assert serialized["mixed"][2] == 1.23

    def test_circular_reference(self):
        a = {}
        b = {"a": a}
        a["b"] = b

        # Serializer should handle this or raise error (currently it will likely RecursionError)
        # We check that it doesn't crash the interpreter at least, or we could implement a check.
        with pytest.raises(RecursionError):
            pytron_serialize(a)

    def test_unknown_type(self):
        class Unknown:
            pass

        # If it doesn't have __dict__ or isn't a known primitive,
        # it should probably return string representation or be handled gracefully
        obj = Unknown()
        serialized = pytron_serialize(obj)
        assert isinstance(serialized, dict) or isinstance(serialized, str)
