"""
File discovery module for finding source code files.
"""
import os
from pathlib import Path
from typing import List
from .unified_config import UnifiedConfig as Config


def discover_source_files(root_path: str) -> List[str]:
    """
    Recursively scans directory tree from root_path and returns list of absolute paths
    for files with supported extensions.
    
    Args:
        root_path: The root directory to scan
        
    Returns:
        List of absolute file paths for supported source files
        
    Raises:
        FileNotFoundError: If root_path doesn't exist
        PermissionError: If unable to access directories
    """
    if not os.path.exists(root_path):
        raise FileNotFoundError(f"Root path does not exist: {root_path}")
    
    if not os.path.isdir(root_path):
        raise ValueError(f"Root path is not a directory: {root_path}")
    
    source_files = []
    root_path = Path(root_path).resolve()
    
    try:
        for item in root_path.rglob('*'):
            try:
                # Skip if it's a directory
                if item.is_dir():
                    continue
                
                # Skip symbolic links to avoid infinite loops
                if item.is_symlink():
                    continue
                
                # Check if any parent directory should be ignored
                if any(ignored_dir in item.parts for ignored_dir in Config.IGNORE_DIRECTORIES):
                    continue
                
                # Check if file has supported extension
                if item.suffix in Config.SUPPORTED_EXTENSIONS:
                    source_files.append(str(item.absolute()))
                    
            except (PermissionError, OSError) as e:
                # Log warning but continue processing other files
                print(f"Warning: Unable to access {item}: {e}")
                continue
                
    except (PermissionError, OSError) as e:
        raise PermissionError(f"Unable to scan directory {root_path}: {e}")
    
    return sorted(source_files)


def get_relative_path(file_path: str, root_path: str) -> str:
    """
    Get relative path of file_path from root_path.
    
    Args:
        file_path: Absolute path to the file
        root_path: Root directory path
        
    Returns:
        Relative path string
    """
    try:
        return str(Path(file_path).relative_to(Path(root_path).resolve()))
    except ValueError:
        # If file is not under root_path, return the absolute path
        return file_path


def create_directory_tree(root_path: str, max_depth: int = 3) -> str:
    """
    Create a text-based directory tree representation.
    
    Args:
        root_path: Root directory to create tree for
        max_depth: Maximum depth to traverse
        
    Returns:
        String representation of directory tree
    """
    def _build_tree(path: Path, prefix: str = "", depth: int = 0) -> List[str]:
        if depth > max_depth:
            return []
        
        items = []
        try:
            # Get all items in directory, sorted
            children = sorted([p for p in path.iterdir() if not p.name.startswith('.')])
            
            # Filter out ignored directories
            children = [p for p in children if p.name not in Config.IGNORE_DIRECTORIES]
            
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                current_prefix = "└── " if is_last else "├── "
                items.append(f"{prefix}{current_prefix}{child.name}")
                
                if child.is_dir() and depth < max_depth:
                    extension = "    " if is_last else "│   "
                    items.extend(_build_tree(child, prefix + extension, depth + 1))
                    
        except (PermissionError, OSError):
            items.append(f"{prefix}└── [Permission Denied]")
            
        return items
    
    root = Path(root_path).resolve()
    tree_lines = [str(root.name)]
    tree_lines.extend(_build_tree(root))
    
    return "\n".join(tree_lines)
