from setuptools import setup

try:
    from setuptools.dist import Distribution

    class BinaryDistribution(Distribution):
        """Force the wheel to be platform-specific."""

        def has_ext_modules(self):
            return True

        def is_pure(self):
            return False

except ImportError:
    BinaryDistribution = None

setup(
    distclass=BinaryDistribution,
)
