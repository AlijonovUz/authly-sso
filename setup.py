from pathlib import Path
from setuptools import setup, find_packages

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="authly-sso",
    version="0.4.1",
    description="Authly SSO OAuth2 integratsiyasi uchun yagona Python / Django SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Authly",
    license="MIT",
    packages=find_packages(include=["authly", "authly.*"]),
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
    keywords=["sso", "authly", "oauth2", "django", "drf", "authentication"],
)
