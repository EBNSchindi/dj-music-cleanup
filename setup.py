#!/usr/bin/env python3
"""
Setup script for DJ Music Library Cleanup Tool
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="dj-music-cleanup",
    version="1.0.0",
    author="DJ Music Cleanup",
    description="Professional DJ music library cleanup and organization tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/dj-music-cleanup",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pyacoustid>=1.2.2",
        "acoustid>=1.3.0",
        "mutagen>=1.46.0",
        "musicbrainzngs>=0.7.1",
        "eyed3>=0.9.7",
        "tqdm>=4.65.0",
        "unidecode>=1.3.6",
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
        ],
        "audio": [
            "librosa>=0.10.0",
            "numpy>=1.24.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "music-cleanup=music_cleanup:main",
        ],
    },
)