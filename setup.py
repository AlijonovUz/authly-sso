from pathlib import Path
from setuptools import setup, find_packages

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="raqamli-passport-sdk",
    version="0.3.0",
    description="Raqamli Nazorat LLC loyihalari uchun yagona SSO Passport SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Raqamli Nazorat LLC",
    license="MIT",
    packages=find_packages(include=["raqamli_passport", "raqamli_passport.*"]),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.28.0",
    ],
    extras_require={
        "django": [
            "django>=4.2",
            "djangorestframework>=3.14.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Framework :: Django",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=["sso", "passport", "oauth2", "django", "drf", "raqamli-nazorat"],
)
