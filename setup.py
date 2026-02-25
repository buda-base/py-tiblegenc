#!/usr/bin/env python3
"""Setup configuration for pytiblegenc package."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="pytiblegenc",
    version="0.2.0",
    description="Python tool for converting PDFs using non-Unicode Tibetan fonts to Unicode text",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="",
    author_email="",
    url="https://github.com/buda-base/py-tiblegenc",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "pdfminer.six>=20221105",
        "fonttools>=4.38.0",
    ],
    package_data={
        "pytiblegenc": [
            "glyph_db.csv",
            "skt_chars.csv",
            "font-tables/*.csv",
        ],
    },
    include_package_data=True,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)

