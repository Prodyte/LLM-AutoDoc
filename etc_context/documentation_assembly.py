"""
Documentation assembly module for generating complete documentation.
"""
import os
from pathlib import Path
from typing import List, Dict
import networkx as nx
from datetime import datetime

from .unified_bedrock_client import UnifiedBedrockClient as BedrockDocumentationClient
from .data_structures import FileInfo
from .dependency_graph import generate_mermaid_graph, get_dependency_stats
from .file_discovery import create_directory_tree, get_relative_path
from .unified_config import UnifiedConfig as Config


def assemble_documentation(repo_path: str, graph: nx.DiGraph, all_file_info: List[FileInfo]) -> None:
    """
    Assemble complete documentation for the repository.
    
    Args:
        repo_path: Path to the repository root
        graph: Dependency graph
        all_file_info: List of all parsed file information
        
    Raises:
        RuntimeError: If documentation generation fails
    """
    print("Initializing AWS Bedrock client...")
    
    # Initialize Bedrock client
    try:
        bedrock_client = BedrockDocumentationClient()
        
        # Validate connection
        if not bedrock_client.validate_connection():
            raise RuntimeError("Failed to connect to AWS Bedrock. Please check your credentials and configuration.")
            
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Bedrock client: {e}")
    
    print("Generating documentation...")
    
    # Generate project summary
    print("  - Generating project overview...")
    project_summary = _generate_project_summary(bedrock_client, repo_path, graph, all_file_info)
    
    # Generate directory tree
    print("  - Creating directory structure...")
    directory_tree = create_directory_tree(repo_path)
    
    # Generate dependency graph
    print("  - Creating dependency graph...")
    mermaid_graph = generate_mermaid_graph(graph)
    dependency_stats = get_dependency_stats(graph)
    
    # Generate documentation for each code unit
    print("  - Generating component documentation...")
    component_docs = _generate_component_documentation(bedrock_client, graph)
    
    # Assemble final documentation
    print("  - Assembling final documentation...")
    final_doc = _assemble_final_documentation(
        project_summary=project_summary,
        directory_tree=directory_tree,
        mermaid_graph=mermaid_graph,
        dependency_stats=dependency_stats,
        component_docs=component_docs,
        repo_path=repo_path
    )
    
    # Write documentation file
    output_path = os.path.join(repo_path, Config.OUTPUT_FILE)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(final_doc)
    
    # Print usage statistics
    usage_stats = bedrock_client.get_usage_stats()
    print(f"\n{'='*60}")
    print(f"📄 DOCUMENTATION GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Output file: {output_path}")
    print(f"Total API requests: {usage_stats['total_requests']}")
    print(f"Total tokens used: {usage_stats['total_tokens_used']:,}")
    
    if usage_stats['total_tokens_used'] > 0:
        estimated_cost = bedrock_client.estimate_cost(
            output_tokens=usage_stats['total_tokens_used']
        )
        print(f"💰 TOTAL ESTIMATED COST: ${estimated_cost:.4f}")
        print(f"{'='*60}")
        
        # Cost breakdown
        print(f"\n💡 Cost Breakdown:")
        print(f"   • Output tokens: {usage_stats['total_tokens_used']:,} @ ~$0.015/1K = ${estimated_cost:.4f}")
        print(f"   • Average cost per component: ${estimated_cost/max(usage_stats['total_requests'], 1):.4f}")
    else:
        print(f"{'='*60}")


def _generate_project_summary(
    bedrock_client: BedrockDocumentationClient,
    repo_path: str,
    graph: nx.DiGraph,
    all_file_info: List[FileInfo]
) -> str:
    """Generate project overview summary using Bedrock."""
    try:
        directory_tree = create_directory_tree(repo_path, max_depth=2)
        # Create a simple project summary prompt
        prompt = f"""
# Project Documentation Request

Please analyze this software project and provide a comprehensive overview.

## Project Structure
{directory_tree}

## Components Summary
- Total files: {len(all_file_info)}
- Functions: {get_dependency_stats(graph)['functions']}
- Classes: {get_dependency_stats(graph)['classes']}
- Methods: {get_dependency_stats(graph)['methods']}

Please provide:
1. Project purpose and main functionality
2. Technology stack analysis
3. Architecture overview
4. Key components and their roles
5. Notable patterns or design decisions

Format the response as a comprehensive markdown document.
"""
        
        # Limit prompt length to avoid token overflow
        if len(prompt) > 6000:
            prompt = prompt[:6000] + "\n\n[Content truncated for token limit]"
        
        summary = bedrock_client.generate_documentation(prompt)
        return summary
        
    except Exception as e:
        print(f"Warning: Failed to generate project summary: {e}")
        return _generate_fallback_project_summary(repo_path, graph, all_file_info)


def _generate_fallback_project_summary(
    repo_path: str,
    graph: nx.DiGraph,
    all_file_info: List[FileInfo]
) -> str:
    """Generate a basic project summary without LLM."""
    stats = get_dependency_stats(graph)
    
    # Count files by type
    file_types = {}
    for file_info in all_file_info:
        ext = file_info.file_path.split('.')[-1].lower()
        file_types[ext] = file_types.get(ext, 0) + 1
    
    repo_name = Path(repo_path).name
    
    summary = f"""# {repo_name}

## Project Overview

This is a software project containing {len(all_file_info)} source files across multiple programming languages.

### Technology Stack
- **Languages**: {', '.join([f'{ext.upper()} ({count} files)' for ext, count in file_types.items()])}
- **Total Components**: {stats['functions']} functions, {stats['classes']} classes, {stats['methods']} methods

### Architecture
- **Total Dependencies**: {stats['total_edges']} relationships between components
- **Internal Dependencies**: {stats['internal_dependencies']}
- **External Dependencies**: {stats['external_dependencies']}
- **Connected Components**: {stats['weakly_connected_components']}

*Note: This is an automatically generated summary. For detailed analysis, please ensure AWS Bedrock is properly configured.*"""
    
    return summary


def _generate_component_documentation(
    bedrock_client: BedrockDocumentationClient,
    graph: nx.DiGraph
) -> Dict[str, Dict[str, str]]:
    """
    Generate documentation for all files (file-level documentation to save costs).
    
    Args:
        bedrock_client: Bedrock client for LLM calls
        graph: Dependency graph
        
    Returns:
        Dictionary organized by file path containing file-level documentation
    """
    component_docs = {}
    
    # Group nodes by file for file-level documentation
    nodes_by_file = {}
    for node_id, node_data in graph.nodes(data=True):
        file_path = node_data.get('relative_path', 'unknown')
        if file_path not in nodes_by_file:
            nodes_by_file[file_path] = []
        nodes_by_file[file_path].append((node_id, node_data))
    
    total_files = len(nodes_by_file)
    processed_files = 0
    
    for file_path, nodes in nodes_by_file.items():
        print(f"    Processing {file_path} ({len(nodes)} components)...")
        
        try:
            # Generate file-level prompt combining all components in the file
            prompt = _generate_file_level_prompt(file_path, nodes, graph)
            
            # Limit prompt length to avoid token overflow
            if len(prompt) > 8000:
                prompt = prompt[:8000] + "\n\n[Content truncated for token limit]"
            
            # Generate documentation for the entire file
            documentation = bedrock_client.generate_documentation(prompt)
            
            # Store file-level documentation
            component_docs[file_path] = {"File Overview": documentation}
            
            processed_files += 1
            current_cost = bedrock_client.estimate_cost(output_tokens=bedrock_client.total_tokens_used)
            print(f"      File {processed_files}/{total_files} documented | Running cost: ${current_cost:.4f}")
            
        except Exception as e:
            print(f"      Warning: Failed to document {file_path}: {e}")
            # Add fallback documentation
            fallback_doc = _generate_fallback_file_doc(file_path, nodes)
            component_docs[file_path] = {"File Overview": fallback_doc}
            processed_files += 1
    
    print(f"    Completed: {processed_files}/{total_files} files documented")
    return component_docs


def _generate_file_level_prompt(file_path: str, nodes: List, graph: nx.DiGraph) -> str:
    """
    Generate a comprehensive prompt for file-level documentation.
    
    Args:
        file_path: Path to the file being documented
        nodes: List of (node_id, node_data) tuples for components in this file
        graph: Dependency graph
        
    Returns:
        Comprehensive prompt for file-level documentation
    """
    prompt_parts = []
    
    # Header
    prompt_parts.append("# File Documentation Request")
    prompt_parts.append(f"Please analyze and document the following source file: `{file_path}`")
    prompt_parts.append("")
    prompt_parts.append("## Instructions")
    prompt_parts.append("Generate comprehensive documentation for this entire file including:")
    prompt_parts.append("1. **File Purpose**: What this file does and its role in the project")
    prompt_parts.append("2. **Key Components**: Overview of main functions, classes, and exports")
    prompt_parts.append("3. **Dependencies**: External libraries and internal modules used")
    prompt_parts.append("4. **Architecture**: How components interact within this file")
    prompt_parts.append("5. **Usage Examples**: How other parts of the codebase might use this file")
    prompt_parts.append("6. **Notable Patterns**: Any design patterns or architectural decisions")
    prompt_parts.append("")
    
    # File overview
    prompt_parts.append("## File Components")
    
    # Group components by type
    functions = []
    classes = []
    methods = []
    
    for node_id, node_data in nodes:
        component_type = node_data.get('type', 'unknown')
        component_name = node_data.get('name', 'unknown')
        code_unit = node_data.get('code_unit')
        
        if component_type == 'function':
            functions.append((component_name, code_unit))
        elif component_type == 'class':
            classes.append((component_name, code_unit))
        elif component_type == 'method':
            methods.append((component_name, code_unit))
    
    # Add component summaries
    if functions:
        prompt_parts.append("### Functions:")
        for name, code_unit in functions[:10]:  # Limit to avoid token overflow
            if hasattr(code_unit, 'parameters'):
                params = ', '.join(code_unit.parameters) if code_unit.parameters else 'none'
                return_type = getattr(code_unit, 'return_type', 'unknown')
                prompt_parts.append(f"- `{name}({params})` → {return_type}")
            else:
                prompt_parts.append(f"- `{name}`")
        if len(functions) > 10:
            prompt_parts.append(f"- ... and {len(functions) - 10} more functions")
        prompt_parts.append("")
    
    if classes:
        prompt_parts.append("### Classes:")
        for name, code_unit in classes[:5]:  # Limit to avoid token overflow
            if hasattr(code_unit, 'methods'):
                method_count = len(code_unit.methods) if code_unit.methods else 0
                prompt_parts.append(f"- `{name}` ({method_count} methods)")
            else:
                prompt_parts.append(f"- `{name}`")
        if len(classes) > 5:
            prompt_parts.append(f"- ... and {len(classes) - 5} more classes")
        prompt_parts.append("")
    
    # Add key source code snippets (limited to avoid token overflow)
    prompt_parts.append("## Key Source Code")
    
    # Include source code for up to 3 main components
    included_components = 0
    for node_id, node_data in nodes:
        if included_components >= 3:
            break
            
        code_unit = node_data.get('code_unit')
        component_name = node_data.get('name', 'unknown')
        
        if hasattr(code_unit, 'source_code') and code_unit.source_code:
            # Limit source code length
            source_code = code_unit.source_code[:1000]
            if len(code_unit.source_code) > 1000:
                source_code += "\n// ... (truncated)"
            
            prompt_parts.append(f"### {component_name}")
            prompt_parts.append("```")
            prompt_parts.append(source_code)
            prompt_parts.append("```")
            prompt_parts.append("")
            included_components += 1
    
    # Add dependency information
    all_dependencies = set()
    for node_id, node_data in nodes:
        code_unit = node_data.get('code_unit')
        if hasattr(code_unit, 'dependencies') and code_unit.dependencies:
            all_dependencies.update(code_unit.dependencies)
    
    if all_dependencies:
        prompt_parts.append("## Dependencies Used")
        for dep in sorted(list(all_dependencies)[:20]):  # Limit to top 20
            prompt_parts.append(f"- {dep}")
        if len(all_dependencies) > 20:
            prompt_parts.append(f"- ... and {len(all_dependencies) - 20} more dependencies")
        prompt_parts.append("")
    
    # Request specific output format
    prompt_parts.append("## Output Format")
    prompt_parts.append("Please provide the documentation in Markdown format with clear sections and subsections.")
    prompt_parts.append("Focus on explaining the file's purpose, architecture, and how it fits into the larger codebase.")
    
    return "\n".join(prompt_parts)


def _generate_fallback_file_doc(file_path: str, nodes: List) -> str:
    """Generate basic fallback documentation for a file."""
    doc_parts = []
    
    doc_parts.append(f"## {file_path}")
    doc_parts.append("")
    doc_parts.append("### File Overview")
    doc_parts.append(f"This file contains {len(nodes)} components.")
    doc_parts.append("")
    
    # Group components by type
    functions = []
    classes = []
    methods = []
    
    for node_id, node_data in nodes:
        component_type = node_data.get('type', 'unknown')
        component_name = node_data.get('name', 'unknown')
        
        if component_type == 'function':
            functions.append(component_name)
        elif component_type == 'class':
            classes.append(component_name)
        elif component_type == 'method':
            methods.append(component_name)
    
    if functions:
        doc_parts.append("### Functions")
        for func in functions[:10]:
            doc_parts.append(f"- `{func}`")
        if len(functions) > 10:
            doc_parts.append(f"- ... and {len(functions) - 10} more functions")
        doc_parts.append("")
    
    if classes:
        doc_parts.append("### Classes")
        for cls in classes[:10]:
            doc_parts.append(f"- `{cls}`")
        if len(classes) > 10:
            doc_parts.append(f"- ... and {len(classes) - 10} more classes")
        doc_parts.append("")
    
    if methods:
        doc_parts.append("### Methods")
        for method in methods[:10]:
            doc_parts.append(f"- `{method}`")
        if len(methods) > 10:
            doc_parts.append(f"- ... and {len(methods) - 10} more methods")
        doc_parts.append("")
    
    doc_parts.append("*Note: Detailed documentation could not be generated. Please ensure AWS Bedrock is properly configured.*")
    
    return "\n".join(doc_parts)


def _generate_fallback_component_doc(component_name: str, component_type: str, code_unit) -> str:
    """Generate basic fallback documentation for a component."""
    doc = f"## {component_name}\n\n"
    doc += f"**Type**: {component_type.title()}\n\n"
    
    if hasattr(code_unit, 'parameters') and code_unit.parameters:
        doc += f"**Parameters**: {', '.join(code_unit.parameters)}\n\n"
    
    if hasattr(code_unit, 'return_type') and code_unit.return_type:
        doc += f"**Return Type**: {code_unit.return_type}\n\n"
    
    if hasattr(code_unit, 'dependencies') and code_unit.dependencies:
        doc += f"**Dependencies**: {', '.join(code_unit.dependencies[:10])}\n\n"
    
    doc += "*Note: Detailed documentation could not be generated. Please ensure AWS Bedrock is properly configured.*\n"
    
    return doc


def _assemble_final_documentation(
    project_summary: str,
    directory_tree: str,
    mermaid_graph: str,
    dependency_stats: Dict,
    component_docs: Dict[str, Dict[str, str]],
    repo_path: str
) -> str:
    """Assemble all documentation sections into final document."""
    
    repo_name = Path(repo_path).name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    doc_sections = []
    
    # Header
    doc_sections.append(f"# {repo_name} - Code Documentation")
    doc_sections.append(f"*Generated on {timestamp}*")
    doc_sections.append("---")
    
    # Table of Contents
    toc = _generate_table_of_contents(component_docs)
    doc_sections.append("## Table of Contents")
    doc_sections.append(toc)
    
    # Project Summary
    doc_sections.append(project_summary)
    
    # Directory Structure
    doc_sections.append("## Directory Structure")
    doc_sections.append("```")
    doc_sections.append(directory_tree)
    doc_sections.append("```")
    
    # Dependency Analysis
    doc_sections.append("## Dependency Analysis")
    doc_sections.append(_format_dependency_stats(dependency_stats))
    
    # Dependency Graph
    doc_sections.append("## Dependency Graph")
    doc_sections.append("```mermaid")
    doc_sections.append(mermaid_graph)
    doc_sections.append("```")
    
    # Component Documentation
    doc_sections.append("## Component Documentation")
    doc_sections.append(_format_component_documentation(component_docs))
    
    # Footer
    doc_sections.append("---")
    doc_sections.append("*This documentation was automatically generated using AWS Bedrock LLM analysis.*")
    
    return "\n\n".join(doc_sections)


def _generate_table_of_contents(component_docs: Dict[str, Dict[str, str]]) -> str:
    """Generate table of contents for the documentation."""
    toc_lines = []
    
    toc_lines.append("1. [Project Overview](#project-overview)")
    toc_lines.append("2. [Directory Structure](#directory-structure)")
    toc_lines.append("3. [Dependency Analysis](#dependency-analysis)")
    toc_lines.append("4. [Dependency Graph](#dependency-graph)")
    toc_lines.append("5. [Component Documentation](#component-documentation)")
    
    for file_path in sorted(component_docs.keys()):
        safe_file_name = file_path.replace('.', '').replace('/', '').replace(' ', '-').lower()
        toc_lines.append(f"   - [{file_path}](#{safe_file_name})")
    
    return "\n".join(toc_lines)


def _format_dependency_stats(stats: Dict) -> str:
    """Format dependency statistics for display."""
    formatted = "### Statistics\n\n"
    formatted += f"- **Total Components**: {stats['total_nodes']}\n"
    formatted += f"- **Functions**: {stats['functions']}\n"
    formatted += f"- **Classes**: {stats['classes']}\n"
    formatted += f"- **Methods**: {stats['methods']}\n"
    formatted += f"- **Total Dependencies**: {stats['total_edges']}\n"
    formatted += f"- **Internal Dependencies**: {stats['internal_dependencies']}\n"
    formatted += f"- **External Dependencies**: {stats['external_dependencies']}\n"
    formatted += f"- **Connected Components**: {stats['weakly_connected_components']}\n"
    
    return formatted


def _format_component_documentation(component_docs: Dict[str, Dict[str, str]]) -> str:
    """Format component documentation for display."""
    formatted_sections = []
    
    for file_path in sorted(component_docs.keys()):
        safe_file_name = file_path.replace('.', '').replace('/', '').replace(' ', '-').lower()
        formatted_sections.append(f"### {file_path} {{#{safe_file_name}}}")
        
        components = component_docs[file_path]
        if not components:
            formatted_sections.append("*No components found in this file.*")
            continue
        
        for component_name, documentation in components.items():
            formatted_sections.append(f"#### {component_name}")
            formatted_sections.append(documentation)
    
    return "\n\n".join(formatted_sections)


def validate_documentation_setup() -> List[str]:
    """
    Validate that all required components are set up for documentation generation.
    
    Returns:
        List of validation errors (empty if all valid)
    """
    errors = []
    
    # Check AWS credentials
    from config import Config
    if not Config.validate_aws_credentials():
        errors.append("AWS credentials not found. Please configure AWS CLI or set environment variables.")
    
    # Check Bedrock client
    try:
        from bedrock_client import BedrockDocumentationClient
        client = BedrockDocumentationClient()
        if not client.validate_connection():
            errors.append("Cannot connect to AWS Bedrock. Please check your region and model access.")
    except Exception as e:
        errors.append(f"Bedrock client error: {e}")
    
    # Check Node.js setup
    try:
        from js_parser import validate_parser_setup
        if not validate_parser_setup():
            errors.append("Node.js parser not set up. Run setup_node_dependencies() first.")
    except Exception as e:
        errors.append(f"JavaScript/TypeScript parser error: {e}")
    
    return errors


def setup_documentation_environment() -> bool:
    """
    Set up the complete documentation environment.
    
    Returns:
        True if setup successful, False otherwise
    """
    print("Setting up documentation environment...")
    
    success = True
    
    # Setup Node.js dependencies
    print("  - Setting up Node.js dependencies...")
    try:
        from js_parser import setup_node_dependencies
        if not setup_node_dependencies():
            print("    Failed to set up Node.js dependencies")
            success = False
        else:
            print("    Node.js dependencies set up successfully")
    except Exception as e:
        print(f"    Error setting up Node.js: {e}")
        success = False
    
    # Validate AWS setup
    print("  - Validating AWS Bedrock setup...")
    try:
        from bedrock_client import BedrockDocumentationClient
        client = BedrockDocumentationClient()
        if client.validate_connection():
            print("    AWS Bedrock connection validated")
        else:
            print("    Warning: AWS Bedrock connection failed")
            success = False
    except Exception as e:
        print(f"    Error validating AWS Bedrock: {e}")
        success = False
    
    if success:
        print("Documentation environment set up successfully!")
    else:
        print("Documentation environment setup completed with warnings/errors.")
    
    return success
