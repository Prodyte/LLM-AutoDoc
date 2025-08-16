"""
JavaScript/TypeScript parser module using Node.js subprocess.
"""
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Optional
from .data_structures import FileInfo, FunctionInfo, ClassInfo


class JSParserError(Exception):
    """Exception raised when JS/TS parsing fails."""
    pass


def parse_js_ts_file(file_path: str, timeout: int = 30) -> Dict:
    """
    Parse JavaScript/TypeScript file using Node.js parser.
    
    Args:
        file_path: Path to the JS/TS file to parse
        timeout: Timeout in seconds for the subprocess
        
    Returns:
        Dictionary containing parsed file information
        
    Raises:
        JSParserError: If parsing fails
        FileNotFoundError: If file doesn't exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Get the directory containing this script
    current_dir = Path(__file__).parent
    parser_script = current_dir / "parsers" / "parser.js"
    
    if not parser_script.exists():
        raise JSParserError(f"Parser script not found: {parser_script}")
    
    try:
        # Run the Node.js parser
        result = subprocess.run(
            ["node", str(parser_script), file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=current_dir
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise JSParserError(f"Parser failed for {file_path}: {error_msg}")
        
        # Parse JSON output
        try:
            parsed_data = json.loads(result.stdout)
            return parsed_data
        except json.JSONDecodeError as e:
            raise JSParserError(f"Failed to parse JSON output: {e}")
            
    except subprocess.TimeoutExpired:
        raise JSParserError(f"Parser timed out after {timeout} seconds for {file_path}")
    except subprocess.SubprocessError as e:
        raise JSParserError(f"Subprocess error: {e}")
    except Exception as e:
        raise JSParserError(f"Unexpected error parsing {file_path}: {e}")


def convert_to_file_info(file_path: str, parsed_data: Dict) -> FileInfo:
    """
    Convert parsed data to FileInfo object.
    
    Args:
        file_path: Path to the source file
        parsed_data: Dictionary from parse_js_ts_file
        
    Returns:
        FileInfo object
    """
    functions = []
    classes = []
    imports = []
    
    # Convert functions
    for func_data in parsed_data.get('functions', []):
        parameters = [param['name'] for param in func_data.get('parameters', [])]
        dependencies = func_data.get('dependencies', [])
        
        function_info = FunctionInfo(
            name=func_data['name'],
            file_path=file_path,
            source_code=func_data.get('source_code', ''),
            dependencies=dependencies,
            parameters=parameters,
            return_type=func_data.get('return_type', 'any')
        )
        functions.append(function_info)
    
    # Convert classes
    for class_data in parsed_data.get('classes', []):
        methods = []
        properties = []
        
        # Convert methods
        for method_data in class_data.get('methods', []):
            method_parameters = [param['name'] for param in method_data.get('parameters', [])]
            method_dependencies = method_data.get('dependencies', [])
            
            method_info = FunctionInfo(
                name=method_data['name'],
                file_path=file_path,
                source_code=method_data.get('source_code', ''),
                dependencies=method_dependencies,
                parameters=method_parameters,
                return_type=method_data.get('return_type', 'any')
            )
            methods.append(method_info)
        
        # Convert properties
        for prop_data in class_data.get('properties', []):
            properties.append(prop_data['name'])
        
        class_dependencies = class_data.get('dependencies', [])
        
        class_info = ClassInfo(
            name=class_data['name'],
            file_path=file_path,
            source_code=class_data.get('source_code', ''),
            dependencies=class_dependencies,
            methods=methods,
            properties=properties
        )
        classes.append(class_info)
    
    # Extract import modules
    for import_data in parsed_data.get('imports', []):
        imports.append(import_data['module'])
    
    return FileInfo(
        file_path=file_path,
        functions=functions,
        classes=classes,
        imports=imports
    )


def setup_node_dependencies(force_install: bool = False) -> bool:
    """
    Setup Node.js dependencies for the parser.
    
    Args:
        force_install: Force reinstall even if node_modules exists
        
    Returns:
        True if setup successful, False otherwise
    """
    current_dir = Path(__file__).parent
    parsers_dir = current_dir / "parsers"
    node_modules = parsers_dir / "node_modules"
    
    if node_modules.exists() and not force_install:
        return True
    
    try:
        # Check if npm is available
        subprocess.run(["npm", "--version"], capture_output=True, check=True)
        
        # Install dependencies
        result = subprocess.run(
            ["npm", "install"],
            cwd=parsers_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("Node.js dependencies installed successfully")
            return True
        else:
            print(f"Failed to install Node.js dependencies: {result.stderr}")
            return False
            
    except subprocess.CalledProcessError:
        print("npm not found. Please install Node.js and npm")
        return False
    except Exception as e:
        print(f"Error setting up Node.js dependencies: {e}")
        return False


def validate_parser_setup() -> bool:
    """
    Validate that the parser setup is correct.
    
    Returns:
        True if setup is valid, False otherwise
    """
    current_dir = Path(__file__).parent
    parser_script = current_dir / "parsers" / "parser.js"
    package_json = current_dir / "parsers" / "package.json"
    node_modules = current_dir / "parsers" / "node_modules"
    
    if not parser_script.exists():
        print(f"Parser script not found: {parser_script}")
        return False
    
    if not package_json.exists():
        print(f"package.json not found: {package_json}")
        return False
    
    if not node_modules.exists():
        print("Node.js dependencies not installed. Run setup_node_dependencies()")
        return False
    
    try:
        # Test the parser with a simple script
        result = subprocess.run(
            ["node", str(parser_script)],
            capture_output=True,
            text=True,
            cwd=current_dir
        )
        
        # Should fail with usage message, but not with module errors
        if "Usage:" in result.stderr:
            return True
        else:
            print(f"Parser validation failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"Parser validation error: {e}")
        return False
