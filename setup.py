from setuptools import setup, find_packages

setup(
    name="pytron",
    version="0.1.0",
    description="An Electron-like library for Python using pywebview",
    author="Ghua8088",
    packages=find_packages(),
    install_requires=[
        "pywebview",
        "pyinstaller",
    ],
    entry_points={
        'console_scripts': [
            'pytron=pytron.cli:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
