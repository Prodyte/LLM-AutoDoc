"""
Data structures for the automated documentation tool.
"""
from dataclasses import dataclass
from typing import List


@dataclass
class CodeUnit:
    """Base class for code units."""
    name: str
    file_path: str
    source_code: str
    dependencies: List[str]  # List of dependency names/identifiers
    documentation: str = ""  # Generated documentation


@dataclass  
class FunctionInfo(CodeUnit):
    """Information about a function or method."""
    parameters: List[str] = None
    return_type: str = ""
    
    def __post_init__(self):
        # Ensure parameters is always a list
        if self.parameters is None:
            self.parameters = []


@dataclass
class ClassInfo(CodeUnit):
    """Information about a class."""
    methods: List[FunctionInfo] = None
    properties: List[str] = None
    
    def __post_init__(self):
        # Ensure methods and properties are always lists
        if self.methods is None:
            self.methods = []
        if self.properties is None:
            self.properties = []


@dataclass
class FileInfo:
    """Information about a source file."""
    file_path: str
    functions: List[FunctionInfo] = None
    classes: List[ClassInfo] = None
    imports: List[str] = None
    
    def __post_init__(self):
        # Ensure all lists are initialized
        if self.functions is None:
            self.functions = []
        if self.classes is None:
            self.classes = []
        if self.imports is None:
            self.imports = []
