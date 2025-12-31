import json
import base64
import io
import datetime
import uuid
import decimal
import pathlib

# Optional dependencies
try:
    import pydantic
except ImportError:
    pydantic = None

try:
    from PIL import Image
except ImportError:
    Image = None


class PytronJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # 1. Pydantic Models
        if pydantic and isinstance(obj, pydantic.BaseModel):
            try:
                return obj.model_dump()
            except AttributeError:
                return obj.dict()

        # 2. PIL Images -> Base64 Data URI
        if Image and isinstance(obj, Image.Image):
            buffered = io.BytesIO()
            obj.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{img_str}"

        # 3. Standard Types
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("utf-8")
        if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
            return obj.isoformat()
        if isinstance(obj, datetime.timedelta):
            return obj.total_seconds()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        if isinstance(obj, pathlib.Path):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, complex):
            return {"real": obj.real, "imag": obj.imag}

        # 4. Enums
        try:
            import enum

            if isinstance(obj, enum.Enum):
                return obj.value
        except ImportError:
            pass

        # 5. Dataclasses
        try:
            import dataclasses

            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
        except ImportError:
            pass

        # 6. Universal Fallback: Try __dict__ / vars() for generic arbitrary objects
        if hasattr(obj, "__dict__"):
            try:
                return vars(obj)
            except TypeError:
                pass  # vars() argument must have __dict__ attribute

        # 6.5 Slots Fallback (for memory optimized objects without __dict__)
        if hasattr(obj, "__slots__"):
            data = {}
            slots = obj.__slots__
            if isinstance(slots, str):
                slots = [slots]
            for key in slots:
                # Skip private attributes and methods mixed into slots
                if not key.startswith("_"):
                    try:
                        data[key] = getattr(obj, key)
                    except Exception:
                        pass
            if data:
                return data

        # 7. Iterables (generators, etc)
        # Note: lists and tuples are handled by standard json encoder,
        # but generic iterators are not.
        try:
            iter(obj)
            # Check length is finite to prevent infinite loops?
            # Safer to just listify standard iterators, but careful with infinite ones.
            # We'll trust the user isn't serializing itertools.count()
            return list(obj)
        except TypeError:
            pass

        # 8. Final attempt: String representation used as last resort?
        # Or let standard encoder raise TypeError.
        # Returning str(obj) is "safe" but might be misleading (e.g. "<MyObj object at ...>")
        # Let's try str() if it has a custom __str__?
        # No, safer to standard error so user knows we couldn't structure it.
        # But user asked for "Universal". So __str__ is the ultimate fallback.
        try:
            return str(obj)
        except Exception:
            return super().default(obj)


def pytron_serialize(obj):
    """
    Helper to serialize objects to JSON-compatible primitives.
    This ensures that return values from Python functions are safe for pywebview to serialize.
    """
    # Optimization: if it's already a primitive, return it
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj

    # Use the encoder to handle everything else recursively
    return json.loads(json.dumps(obj, cls=PytronJSONEncoder))
