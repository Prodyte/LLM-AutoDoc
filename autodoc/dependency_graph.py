"""
Dependency graph construction module using NetworkX.
"""
import networkx as nx
from typing import List, Dict, Set
from .data_structures import FileInfo, CodeUnit, FunctionInfo, ClassInfo
from pathlib import Path


def build_dependency_graph(all_file_info: List[FileInfo]) -> nx.DiGraph:
    """
    Build a dependency graph from parsed file information.
    
    Args:
        all_file_info: List of FileInfo objects containing parsed code information
        
    Returns:
        NetworkX DiGraph with nodes representing code units and edges representing dependencies
    """
    graph = nx.DiGraph()
    
    # First pass: Add all nodes
    for file_info in all_file_info:
        _add_nodes_from_file(graph, file_info)
    
    # Second pass: Add edges based on dependencies
    for file_info in all_file_info:
        _add_edges_from_file(graph, file_info, all_file_info)
    
    return graph


def _add_nodes_from_file(graph: nx.DiGraph, file_info: FileInfo) -> None:
    """
    Add nodes to the graph from a single file's information.
    
    Args:
        graph: NetworkX DiGraph to add nodes to
        file_info: FileInfo object containing parsed code information
    """
    relative_path = _get_relative_path(file_info.file_path)
    
    # Add function nodes
    for function in file_info.functions:
        node_id = f"{relative_path}#{function.name}"
        graph.add_node(
            node_id,
            code_unit=function,
            type='function',
            file_path=file_info.file_path,
            relative_path=relative_path,
            name=function.name
        )
    
    # Add class nodes and their methods
    for class_info in file_info.classes:
        class_node_id = f"{relative_path}#{class_info.name}"
        graph.add_node(
            class_node_id,
            code_unit=class_info,
            type='class',
            file_path=file_info.file_path,
            relative_path=relative_path,
            name=class_info.name
        )
        
        # Add method nodes
        for method in class_info.methods:
            method_node_id = f"{relative_path}#{class_info.name}.{method.name}"
            graph.add_node(
                method_node_id,
                code_unit=method,
                type='method',
                file_path=file_info.file_path,
                relative_path=relative_path,
                name=method.name,
                parent_class=class_info.name
            )


def _add_edges_from_file(graph: nx.DiGraph, file_info: FileInfo, all_file_info: List[FileInfo]) -> None:
    """
    Add dependency edges to the graph from a single file's information.
    
    Args:
        graph: NetworkX DiGraph to add edges to
        file_info: FileInfo object containing parsed code information
        all_file_info: List of all FileInfo objects for cross-file dependency resolution
    """
    relative_path = _get_relative_path(file_info.file_path)
    
    # Create a lookup for all available code units
    all_code_units = _build_code_unit_lookup(all_file_info)
    
    # Add edges for functions
    for function in file_info.functions:
        source_node_id = f"{relative_path}#{function.name}"
        _add_dependency_edges(graph, source_node_id, function.dependencies, all_code_units, file_info)
    
    # Add edges for classes and their methods
    for class_info in file_info.classes:
        class_node_id = f"{relative_path}#{class_info.name}"
        _add_dependency_edges(graph, class_node_id, class_info.dependencies, all_code_units, file_info)
        
        # Add edges for methods
        for method in class_info.methods:
            method_node_id = f"{relative_path}#{class_info.name}.{method.name}"
            _add_dependency_edges(graph, method_node_id, method.dependencies, all_code_units, file_info)
            
            # Add edge from method to its parent class
            if graph.has_node(class_node_id):
                graph.add_edge(method_node_id, class_node_id, relationship='member_of')


def _build_code_unit_lookup(all_file_info: List[FileInfo]) -> Dict[str, List[str]]:
    """
    Build a lookup dictionary for code unit names to their node IDs.
    
    Args:
        all_file_info: List of all FileInfo objects
        
    Returns:
        Dictionary mapping code unit names to lists of possible node IDs
    """
    lookup = {}
    
    for file_info in all_file_info:
        relative_path = _get_relative_path(file_info.file_path)
        
        # Add functions
        for function in file_info.functions:
            name = function.name
            node_id = f"{relative_path}#{name}"
            if name not in lookup:
                lookup[name] = []
            lookup[name].append(node_id)
        
        # Add classes
        for class_info in file_info.classes:
            name = class_info.name
            node_id = f"{relative_path}#{name}"
            if name not in lookup:
                lookup[name] = []
            lookup[name].append(node_id)
            
            # Add methods
            for method in class_info.methods:
                method_name = method.name
                method_node_id = f"{relative_path}#{class_info.name}.{method_name}"
                if method_name not in lookup:
                    lookup[method_name] = []
                lookup[method_name].append(method_node_id)
    
    return lookup


def _add_dependency_edges(
    graph: nx.DiGraph, 
    source_node_id: str, 
    dependencies: List[str], 
    all_code_units: Dict[str, List[str]],
    current_file_info: FileInfo
) -> None:
    """
    Add dependency edges from a source node to its dependencies.
    
    Args:
        graph: NetworkX DiGraph to add edges to
        source_node_id: ID of the source node
        dependencies: List of dependency names
        all_code_units: Lookup dictionary for code unit names
        current_file_info: FileInfo for the current file (for same-file dependencies)
    """
    if not graph.has_node(source_node_id):
        return
    
    current_relative_path = _get_relative_path(current_file_info.file_path)
    
    for dep_name in dependencies:
        # Skip common language keywords and built-ins
        if _is_builtin_or_keyword(dep_name):
            continue
        
        target_node_ids = all_code_units.get(dep_name, [])
        
        for target_node_id in target_node_ids:
            if target_node_id != source_node_id and graph.has_node(target_node_id):
                # Determine relationship type
                if current_relative_path in target_node_id:
                    relationship = 'internal_dependency'
                else:
                    relationship = 'external_dependency'
                
                graph.add_edge(source_node_id, target_node_id, relationship=relationship)


def _get_relative_path(file_path: str) -> str:
    """
    Get a relative path representation for consistent node naming.
    
    Args:
        file_path: Absolute file path
        
    Returns:
        Relative path string
    """
    return str(Path(file_path).name)


def _is_builtin_or_keyword(name: str) -> bool:
    """
    Check if a name is a built-in function, keyword, or common library.
    
    Args:
        name: Name to check
        
    Returns:
        True if the name should be ignored as a dependency
    """
    # Common JavaScript/TypeScript built-ins and keywords
    js_builtins = {
        'console', 'window', 'document', 'Array', 'Object', 'String', 'Number', 'Boolean',
        'Date', 'Math', 'JSON', 'Promise', 'setTimeout', 'setInterval', 'clearTimeout',
        'clearInterval', 'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'undefined', 'null',
        'true', 'false', 'this', 'super', 'new', 'typeof', 'instanceof', 'in', 'of',
        'for', 'while', 'do', 'if', 'else', 'switch', 'case', 'default', 'break', 'continue',
        'function', 'return', 'var', 'let', 'const', 'class', 'extends', 'import', 'export',
        'from', 'as', 'default', 'async', 'await', 'try', 'catch', 'finally', 'throw'
    }
    
    # Common single-character or very short names that are likely variables
    short_names = {'i', 'j', 'k', 'x', 'y', 'z', 'a', 'b', 'c', 'e', 'f', 'n', 'm', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w'}
    
    return (
        name in js_builtins or 
        name in short_names or
        len(name) <= 1 or
        name.isdigit()
    )


def get_dependency_stats(graph: nx.DiGraph) -> Dict[str, int]:
    """
    Get statistics about the dependency graph.
    
    Args:
        graph: NetworkX DiGraph
        
    Returns:
        Dictionary with graph statistics
    """
    return {
        'total_nodes': graph.number_of_nodes(),
        'total_edges': graph.number_of_edges(),
        'functions': len([n for n, d in graph.nodes(data=True) if d.get('type') == 'function']),
        'classes': len([n for n, d in graph.nodes(data=True) if d.get('type') == 'class']),
        'methods': len([n for n, d in graph.nodes(data=True) if d.get('type') == 'method']),
        'internal_dependencies': len([e for e in graph.edges(data=True) if e[2].get('relationship') == 'internal_dependency']),
        'external_dependencies': len([e for e in graph.edges(data=True) if e[2].get('relationship') == 'external_dependency']),
        'strongly_connected_components': len(list(nx.strongly_connected_components(graph))),
        'weakly_connected_components': len(list(nx.weakly_connected_components(graph)))
    }


def generate_mermaid_graph(graph: nx.DiGraph, max_nodes: int = 50) -> str:
    """
    Generate Mermaid diagram syntax for the dependency graph.
    
    Args:
        graph: NetworkX DiGraph
        max_nodes: Maximum number of nodes to include in the diagram
        
    Returns:
        Mermaid diagram syntax as string
    """
    if graph.number_of_nodes() == 0:
        return "graph TD\n    A[No dependencies found]"
    
    # Get the most connected nodes if we need to limit
    nodes_to_include = list(graph.nodes())
    if len(nodes_to_include) > max_nodes:
        # Sort by degree (in + out) and take the most connected
        node_degrees = [(node, graph.in_degree(node) + graph.out_degree(node)) for node in nodes_to_include]
        node_degrees.sort(key=lambda x: x[1], reverse=True)
        nodes_to_include = [node for node, _ in node_degrees[:max_nodes]]
    
    mermaid_lines = ["graph TD"]
    
    # Add nodes with labels
    node_labels = {}
    for i, node_id in enumerate(nodes_to_include):
        node_data = graph.nodes[node_id]
        node_type = node_data.get('type', 'unknown')
        name = node_data.get('name', 'unknown')
        
        # Create a short label
        if node_type == 'method':
            parent_class = node_data.get('parent_class', '')
            label = f"{parent_class}.{name}" if parent_class else name
        else:
            label = name
        
        # Truncate long labels
        if len(label) > 20:
            label = label[:17] + "..."
        
        node_key = f"N{i}"
        node_labels[node_id] = node_key
        
        # Style based on type
        if node_type == 'class':
            mermaid_lines.append(f"    {node_key}[{label}]")
            mermaid_lines.append(f"    {node_key} --> {node_key}")  # Self-reference for styling
        elif node_type == 'function':
            mermaid_lines.append(f"    {node_key}({label})")
        elif node_type == 'method':
            mermaid_lines.append(f"    {node_key}[{label}]")
        else:
            mermaid_lines.append(f"    {node_key}[{label}]")
    
    # Add edges
    for source, target in graph.edges():
        if source in node_labels and target in node_labels:
            source_key = node_labels[source]
            target_key = node_labels[target]
            mermaid_lines.append(f"    {source_key} --> {target_key}")
    
    return "\n".join(mermaid_lines)


def find_circular_dependencies(graph: nx.DiGraph) -> List[List[str]]:
    """
    Find circular dependencies in the graph.
    
    Args:
        graph: NetworkX DiGraph
        
    Returns:
        List of cycles, where each cycle is a list of node IDs
    """
    try:
        cycles = list(nx.simple_cycles(graph))
        return cycles
    except nx.NetworkXError:
        return []


def get_most_dependent_nodes(graph: nx.DiGraph, top_n: int = 10) -> List[tuple]:
    """
    Get the nodes with the most dependencies (highest out-degree).
    
    Args:
        graph: NetworkX DiGraph
        top_n: Number of top nodes to return
        
    Returns:
        List of tuples (node_id, out_degree, node_data)
    """
    node_degrees = []
    for node_id in graph.nodes():
        out_degree = graph.out_degree(node_id)
        node_data = graph.nodes[node_id]
        node_degrees.append((node_id, out_degree, node_data))
    
    # Sort by out-degree in descending order
    node_degrees.sort(key=lambda x: x[1], reverse=True)
    
    return node_degrees[:top_n]


def get_most_depended_upon_nodes(graph: nx.DiGraph, top_n: int = 10) -> List[tuple]:
    """
    Get the nodes that are most depended upon (highest in-degree).
    
    Args:
        graph: NetworkX DiGraph
        top_n: Number of top nodes to return
        
    Returns:
        List of tuples (node_id, in_degree, node_data)
    """
    node_degrees = []
    for node_id in graph.nodes():
        in_degree = graph.in_degree(node_id)
        node_data = graph.nodes[node_id]
        node_degrees.append((node_id, in_degree, node_data))
    
    # Sort by in-degree in descending order
    node_degrees.sort(key=lambda x: x[1], reverse=True)
    
    return node_degrees[:top_n]
