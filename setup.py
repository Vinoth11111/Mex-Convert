#!/usr/bin/env python3
"""Setup script for Elumichai."""

from setuptools import setup, find_packages

setup(
    name="elumichai",
    version="1.0.0",
    description="Free, offline file conversion tool for Linux — inspired by Tangerine for macOS",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Open Source Community",
    license="MIT",
    python_requires=">=3.9",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "elumichai=citrus_converter.main:main",
            "elumichai-cli=citrus_converter.cli:main",
        ],
    },
    install_requires=[
        "PySide6>=6.5",
        # All other deps are system tools (ffmpeg, imagemagick, etc.)
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
        "Topic :: Multimedia :: Video :: Conversion",
    ],
)
