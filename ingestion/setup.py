"""
Package setup for ctgov_ingestion.

Build as a Python wheel for upload to Databricks:
    pip install build
    python -m build --wheel
    # Upload dist/ctgov_ingestion-1.0.0-py3-none-any.whl to Databricks workspace
"""

from setuptools import find_packages, setup

setup(
    name="ctgov_ingestion",
    version="1.0.0",
    description="ClinicalTrials.gov v2 API ingestion pipeline for Databricks",
    author="Jyoti",
    author_email="",
    python_requires=">=3.9",
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "requests>=2.31.0",
        "azure-storage-file-datalake>=12.14.0",
        "azure-identity>=1.15.0",
    ],
    entry_points={
        "console_scripts": [
            # Referenced in Databricks python_wheel_task.entry_point
            "main=ctgov_ingestion.main:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
