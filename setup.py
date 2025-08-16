from setuptools import setup, find_packages

setup(
    name="LLM-AutoDoc",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "PyGithub>=2.1.1",
        "requests>=2.31.0",
        "boto3>=1.37.0",
        "botocore>=1.24.0"
    ],
    entry_points={
        'console_scripts': [
            'etc-pr=LLM-AutoDoc.cli:main',
            'autodoc=LLM-AutoDoc.unified_cli:main',
        ],
    },
    author="",
    description="A tool to fetch and analyze GitHub PR comments and context",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/LLM-AutoDoc",
    python_requires=">=3.6",
)
