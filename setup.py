#!/usr/bin/env python
"""Setup configuration for quant_stickynote package."""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="quant_stickynote",
    version="0.1.0",
    author="Your Team",
    author_email="team@example.com",
    description="Backend service for continuous stock trading signal discovery",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/mayberryjp/quant_stickynote",
    project_urls={
        "Bug Tracker": "https://github.com/mayberryjp/quant_stickynote/issues",
        "Documentation": "https://github.com/mayberryjp/quant_stickynote/blob/main/SPEC.md",
        "Source Code": "https://github.com/mayberryjp/quant_stickynote",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.12",
    install_requires=[
        # Core dependencies
        "bottle==0.12.25",
        "waitress==2.1.2",
        "sqlalchemy==2.0.23",
        "psycopg[binary]==3.1.13",
        "pydantic-settings==2.1.0",
        "pydantic==2.5.0",
        "alembic==1.12.1",
        # Utilities
        "python-dotenv==1.0.0",
        "structlog==24.1.0",
    ],
    extras_require={
        "dev": [
            "pytest==7.4.3",
            "pytest-cov==4.1.0",
            "pytest-watch==4.2.0",
            "black==23.12.0",
            "flake8==6.1.0",
            "isort==5.13.2",
            "mypy==1.7.1",
        ],
        "docs": [
            "sphinx==7.2.6",
            "sphinx-rtd-theme==2.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Utilities",
    ],
    entry_points={
        "console_scripts": [
            "quant-stickynote=quant_stickynote.main:cli",
        ],
    },
)
