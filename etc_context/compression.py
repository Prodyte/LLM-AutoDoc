"""
Markdown to SKF (Structured Knowledge Format) Converter

This module takes a markdown documentation file and converts it to the
machine-optimized SKF format for efficient AI parsing.
"""

import re
import json
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import datetime


class MarkdownToSKFConverter:
    """
    Converts markdown documentation to SKF format by parsing the structure
    and extracting definitions, interactions, and usage patterns.
    """
    
    def __init__(self):
        self.definitions = []
        self.interactions = []
        self.usage_patterns = []
        self.global_id_counter = 1
        self.def_id_counter = 1
        self.interaction_id_counter = 1
        
    def convert_md_to_skf(self, md_content: str, source_name: str = "documentation") -> str:
        """
        Convert markdown content to SKF format.
        
        Args:
            md_content: The markdown content to convert
            source_name: Name of the source document
            
        Returns:
            SKF formatted string
        """
        # Reset counters
        self._reset_counters()
        
        # Parse markdown structure
        sections = self._parse_markdown_sections(md_content)
        
        # Extract primary namespace from title or first heading
        primary_namespace = self._extract_primary_namespace(sections)
        
        # Process sections into SKF components
        self._process_sections(sections)
        
        # Generate SKF content
        return self._generate_skf_content([source_name], primary_namespace)
    
    def _reset_counters(self):
        """Reset all counters and collections."""
        self.definitions.clear()
        self.interactions.clear()
        self.usage_patterns.clear()
        self.global_id_counter = 1
        self.def_id_counter = 1
        self.interaction_id_counter = 1
    
    def _parse_markdown_sections(self, content: str) -> List[Dict]:
        """Parse markdown into structured sections."""
        sections = []
        lines = content.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            # Check for headers
            header_match = re.match(r'^(#{1,6})\s+(.+)', line)
            if header_match:
                # Save previous section
                if current_section:
                    current_section['content'] = '\n'.join(current_content)
                    sections.append(current_section)
                
                # Start new section
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_section = {
                    'level': level,
                    'title': title,
                    'content': '',
                    'type': self._classify_section_type(title)
                }
                current_content = []
            else:
                if current_section:
                    current_content.append(line)
        
        # Add last section
        if current_section:
            current_section['content'] = '\n'.join(current_content)
            sections.append(current_section)
        
        return sections
    
    def _classify_section_type(self, title: str) -> str:
        """Classify section type based on title."""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['class', 'component', 'module', 'service']):
            return 'component'
        elif any(word in title_lower for word in ['function', 'method', 'api', 'endpoint']):
            return 'function'
        elif any(word in title_lower for word in ['usage', 'example', 'how to', 'tutorial']):
            return 'usage'
        elif any(word in title_lower for word in ['dependency', 'import', 'require']):
            return 'dependency'
        elif any(word in title_lower for word in ['architecture', 'design', 'pattern']):
            return 'architecture'
        else:
            return 'general'
    
    def _extract_primary_namespace(self, sections: List[Dict]) -> str:
        """Extract primary namespace from sections."""
        if sections:
            first_section = sections[0]
            title = first_section['title']
            
            # Clean up title to create namespace
            namespace = re.sub(r'[^\w\s-]', '', title)
            namespace = re.sub(r'\s+', '_', namespace.strip())
            return namespace.lower()
        
        return "documentation"
    
    def _process_sections(self, sections: List[Dict]):
        """Process sections into SKF components."""
        for section in sections:
            if section['type'] == 'component':
                self._process_component_section(section)
            elif section['type'] == 'function':
                self._process_function_section(section)
            elif section['type'] == 'usage':
                self._process_usage_section(section)
            elif section['type'] == 'dependency':
                self._process_dependency_section(section)
    
    def _process_component_section(self, section: Dict):
        """Process a component section into SKF definition."""
        global_id = f"G{self.global_id_counter:03d}_{self._clean_name(section['title'])}"
        def_id = f"D{self.def_id_counter:03d}:{global_id}"
        
        # Extract operations from content
        operations = self._extract_operations_from_content(section['content'])
        
        # Extract attributes
        attributes = self._extract_attributes_from_content(section['content'])
        
        definition = {
            'id': def_id,
            'global_id': global_id,
            'entity_name': section['title'],
            'def_type': 'CompDef',
            'namespace': '.',
            'operations': operations,
            'attributes': attributes,
            'note': self._extract_brief_description(section['content'])
        }
        
        self.definitions.append(definition)
        self.global_id_counter += 1
        self.def_id_counter += 1
    
    def _process_function_section(self, section: Dict):
        """Process a function section into SKF definition."""
        global_id = f"G{self.global_id_counter:03d}_{self._clean_name(section['title'])}"
        def_id = f"D{self.def_id_counter:03d}:{global_id}"
        
        # Extract function signature
        operations = self._extract_function_signature(section['content'], section['title'])
        
        definition = {
            'id': def_id,
            'global_id': global_id,
            'entity_name': section['title'],
            'def_type': 'FuncDef',
            'namespace': '.',
            'operations': operations,
            'attributes': {},
            'note': self._extract_brief_description(section['content'])
        }
        
        self.definitions.append(definition)
        self.global_id_counter += 1
        self.def_id_counter += 1
    
    def _process_usage_section(self, section: Dict):
        """Process a usage section into SKF usage pattern."""
        pattern_name = f"U_{self._clean_name(section['title'])}"
        
        # Extract steps from content
        steps = self._extract_usage_steps(section['content'])
        
        pattern = {
            'name': pattern_name,
            'title': section['title'],
            'steps': steps
        }
        
        self.usage_patterns.append(pattern)
    
    def _process_dependency_section(self, section: Dict):
        """Process a dependency section into SKF interactions."""
        dependencies = self._extract_dependencies_from_content(section['content'])
        
        for dep in dependencies:
            interaction = {
                'id': f"I{self.interaction_id_counter:03d}",
                'source_ref': 'system',
                'verb': 'IMPORTS',
                'target_ref': dep,
                'note': f"System imports {dep}"
            }
            self.interactions.append(interaction)
            self.interaction_id_counter += 1
    
    def _extract_operations_from_content(self, content: str) -> Dict[str, str]:
        """Extract operations/methods from content."""
        operations = {}
        
        # Look for method patterns
        method_patterns = [
            r'`(\w+)\([^)]*\)(?:\s*:\s*(\w+))?`',  # `method(params): ReturnType`
            r'(\w+)\([^)]*\)(?:\s*->\s*(\w+))?',   # method(params) -> ReturnType
            r'def\s+(\w+)\([^)]*\)(?:\s*:\s*(\w+))?',  # def method(params): ReturnType
        ]
        
        for pattern in method_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    method_name = match[0]
                    return_type = match[1] if len(match) > 1 and match[1] else 'Any'
                else:
                    method_name = match
                    return_type = 'Any'
                
                operations[method_name] = f"{return_type}()"
        
        return operations
    
    def _extract_attributes_from_content(self, content: str) -> Dict[str, str]:
        """Extract attributes/properties from content."""
        attributes = {}
        
        # Look for property patterns
        property_patterns = [
            r'`(\w+):\s*(\w+)`',  # `property: Type`
            r'(\w+)\s*:\s*(\w+)',  # property: Type
        ]
        
        for pattern in property_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple) and len(match) == 2:
                    prop_name, prop_type = match
                    attributes[prop_name] = prop_type
        
        return attributes
    
    def _extract_function_signature(self, content: str, title: str) -> Dict[str, str]:
        """Extract function signature from content."""
        operations = {}
        
        # Try to find function signature in content
        func_patterns = [
            r'`([^`]+\([^)]*\)(?:\s*:\s*\w+)?)`',
            r'(\w+\([^)]*\)(?:\s*->\s*\w+)?)',
        ]
        
        for pattern in func_patterns:
            matches = re.findall(pattern, content)
            if matches:
                operations[self._clean_name(title)] = matches[0]
                break
        
        if not operations:
            # Fallback to title-based signature
            operations[self._clean_name(title)] = "Any()"
        
        return operations
    
    def _extract_usage_steps(self, content: str) -> List[Tuple[str, str, str, str]]:
        """Extract usage steps from content."""
        steps = []
        
        # Look for numbered steps or bullet points
        step_patterns = [
            r'(\d+)\.\s*(.+)',  # 1. Step description
            r'[-*]\s*(.+)',     # - Step description
        ]
        
        step_counter = 1
        for pattern in step_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    step_desc = match[1] if len(match) > 1 else match[0]
                else:
                    step_desc = match
                
                # Parse step into actor, action, result
                actor, action, result = self._parse_step_description(step_desc)
                
                steps.append((
                    f"U_Step.{step_counter}",
                    actor,
                    action,
                    result
                ))
                step_counter += 1
        
        return steps
    
    def _parse_step_description(self, description: str) -> Tuple[str, str, str]:
        """Parse step description into actor, action, result."""
        # Simple parsing - can be enhanced
        if '->' in description:
            parts = description.split('->')
            action_part = parts[0].strip()
            result = parts[1].strip()
        else:
            action_part = description.strip()
            result = "[result]"
        
        # Extract actor and action
        if action_part.lower().startswith(('create', 'instantiate', 'new')):
            actor = "[User]"
            action = "CREATE"
        elif action_part.lower().startswith(('call', 'invoke', 'execute')):
            actor = "[instance]"
            action = "INVOKE"
        else:
            actor = "[User]"
            action = "ACTION"
        
        return actor, action, f"({action_part}) -> [{result}]"
    
    def _extract_dependencies_from_content(self, content: str) -> List[str]:
        """Extract dependencies from content."""
        dependencies = []
        
        # Look for import/dependency patterns
        dep_patterns = [
            r'import\s+([^\s;]+)',
            r'require\s*\([\'"]([^\'"]+)[\'"]\)',
            r'from\s+([^\s]+)\s+import',
            r'`([^`]+)`',  # Backtick-quoted dependencies
        ]
        
        for pattern in dep_patterns:
            matches = re.findall(pattern, content)
            dependencies.extend(matches)
        
        return list(set(dependencies))  # Remove duplicates
    
    def _extract_brief_description(self, content: str) -> str:
        """Extract brief description from content."""
        # Take first paragraph or first sentence
        paragraphs = content.strip().split('\n\n')
        if paragraphs:
            first_para = paragraphs[0].strip()
            # Remove markdown formatting
            first_para = re.sub(r'[*_`#]', '', first_para)
            # Take first sentence
            sentences = re.split(r'[.!?]+', first_para)
            if sentences:
                first_sentence = sentences[0].strip()
                if len(first_sentence) > 100:
                    return first_sentence[:97] + "..."
                return first_sentence
        return ""
    
    def _clean_name(self, name: str) -> str:
        """Clean name for use as identifier."""
        # Remove special characters and spaces
        cleaned = re.sub(r'[^\w\s-]', '', name)
        cleaned = re.sub(r'\s+', '_', cleaned.strip())
        return cleaned
    
    def _generate_skf_content(self, source_docs: List[str], primary_namespace: str) -> str:
        """Generate the complete SKF formatted content."""
        lines = []
        
        # Header
        lines.append("# IntegratedKnowledgeManifest_SKF/1.4 LA")
        lines.append(f"# SourceDocs: {json.dumps(source_docs)}")
        lines.append(f"# GenerationTimestamp: {datetime.utcnow().isoformat()}Z")
        lines.append(f"# PrimaryNamespace: {primary_namespace}")
        lines.append("")
        
        # DEFINITIONS Section
        lines.append("# SECTION: DEFINITIONS (Prefix: D)")
        lines.append("# Format_PrimaryDef: Dxxx:Gxxx_Entity [DEF_TYP] [NAMESPACE \"relative.path\"] [OPERATIONS {op1:RetT(p1N:p1T)}] [ATTRIBUTES {attr1:AttrT1}] (\"Note\")")
        lines.append("# ---")
        
        for definition in self.definitions:
            line_parts = [definition['id']]
            line_parts.append(f"[{definition['def_type']}]")
            line_parts.append(f"[NAMESPACE \"{definition['namespace']}\"]")
            
            if definition['operations']:
                ops_str = ",".join([f"{k}:{v}" for k, v in definition['operations'].items()])
                line_parts.append(f"[OPERATIONS {{{ops_str}}}]")
            
            if definition['attributes']:
                attrs_str = ",".join([f"{k}:{v}" for k, v in definition['attributes'].items()])
                line_parts.append(f"[ATTRIBUTES {{{attrs_str}}}]")
            
            if definition['note']:
                line_parts.append(f"(\"{definition['note']}\")")
            
            lines.append(" ".join(line_parts))
        
        lines.append("# ---")
        lines.append("")
        
        # INTERACTIONS Section
        lines.append("# SECTION: INTERACTIONS (Prefix: I)")
        lines.append("# Format: Ixxx:Source_Ref INT_VERB Target_Ref_Or_Literal (\"Note_Conditions_Error(Gxxx_ErrorType)\")")
        lines.append("# ---")
        
        for interaction in self.interactions:
            line_parts = [f"{interaction['id']}:{interaction['source_ref']}"]
            line_parts.append(interaction['verb'])
            line_parts.append(interaction['target_ref'])
            
            if interaction['note']:
                line_parts.append(f"(\"{interaction['note']}\")")
            
            lines.append(" ".join(line_parts))
        
        lines.append("# ---")
        lines.append("")
        
        # USAGE_PATTERNS Section
        lines.append("# SECTION: USAGE_PATTERNS (Prefix: U)")
        lines.append("# Format: U_Name:PatternTitleKeyword")
        lines.append("#         U_Name.N:[Actor_Or_Ref] ACTION_KEYWORD (Target_Or_Data_Involving_Ref) -> [Result_Or_State_Change_Involving_Ref]")
        lines.append("# ---")
        
        for pattern in self.usage_patterns:
            lines.append(f"{pattern['name']}:{pattern['title']}")
            for step_id, actor, action, result in pattern['steps']:
                lines.append(f"{step_id}:{actor} {action} {result}")
        
        lines.append("# ---")
        lines.append("# END_OF_MANIFEST")
        
        return "\n".join(lines)


def compress_markdown_to_skf(md_content: str, source_name: str = "documentation") -> Tuple[str, Dict[str, any]]:
    """
    Convert markdown content to SKF format and return compression stats.
    
    Args:
        md_content: The markdown content to convert
        source_name: Name of the source document
        
    Returns:
        Tuple of (SKF content, compression stats)
    """
    converter = MarkdownToSKFConverter()
    skf_content = converter.convert_md_to_skf(md_content, source_name)
    
    # Calculate compression stats
    original_size = len(md_content)
    compressed_size = len(skf_content)
    reduction = (original_size - compressed_size) / original_size if original_size > 0 else 0
    
    stats = {
        'original_size': original_size,
        'compressed_size': compressed_size,
        'compression_ratio': reduction,
        'size_change': 'compressed' if reduction > 0 else 'expanded'
    }
    
    return skf_content, stats


def generate_skf_decoding_guidelines(skf_content: str, project_name: str, stats: Dict[str, any]) -> str:
    """
    Generate comprehensive decoding guidelines for an SKF file using LLM analysis.
    
    Args:
        skf_content: The SKF content to analyze
        project_name: Name of the project
        stats: Compression statistics
        
    Returns:
        Markdown formatted decoding guidelines
    """
    from .unified_bedrock_client import UnifiedBedrockClient
    from .unified_config import UnifiedConfig
    
    try:
        # Initialize Bedrock client
        bedrock_client = UnifiedBedrockClient()
        
        # Create analysis prompt
        prompt = f"""
# SKF Decoding Guidelines Generation Task

You are tasked with creating comprehensive decoding guidelines for a Structured Knowledge Format (SKF) file. Analyze the provided SKF content and generate detailed instructions for understanding and decoding it.

## Project Information
- **Project Name**: {project_name}
- **Original Size**: {stats.get('original_size', 0):,} characters
- **SKF Size**: {stats.get('compressed_size', 0):,} characters
- **Compression Ratio**: {stats.get('compression_ratio', 0):.1%} reduction

## SKF Content to Analyze:
```
{skf_content[:8000]}{"..." if len(skf_content) > 8000 else ""}
```

## Required Output Format

Generate a comprehensive markdown document with the following structure:

# SKF Format Decoding Guidelines

## Overview
Brief description of the SKF format and its purpose for this specific project.

## Header Metadata
Explain each header field found in the SKF file:
- Format identifier and version
- Source documents
- Generation timestamp
- Primary namespace

## Section Formats

### DEFINITIONS (Prefix: D)
Explain the format: `Dxxx:Gxxx_Entity [DEF_TYP] [NAMESPACE "path"] [OPERATIONS {{...}}] [ATTRIBUTES {{...}}] ("Note")`

**Field Meanings:**
- Detailed explanation of each field
- What DEF_TYP values mean (CompDef, FuncDef, etc.)
- How to interpret OPERATIONS and ATTRIBUTES

**Examples from the file:**
Include 2-3 actual examples from the provided SKF content

### INTERACTIONS (Prefix: I)
Explain the format: `Ixxx:Source_Ref VERB Target_Ref ("Note")`

**Interaction Verbs:**
List and explain the verbs found (INVOKES, IMPORTS, USES_COMPONENT, etc.)

**Examples from the file:**
Include actual examples

### USAGE_PATTERNS (Prefix: U)
Explain the format and provide examples

## Key Components Identified

### Major Service Components
List the main components found in the SKF file with brief descriptions

### Infrastructure Components
List infrastructure/utility components

### Data Models
List data models/entities if present

## Usage Instructions

Provide step-by-step instructions for:
1. Finding specific components
2. Understanding relationships
3. Following usage patterns
4. Understanding the service architecture

## Compression Statistics
Include the provided statistics and explain the efficiency gains

Focus on making this guide practical and actionable for developers who need to understand the codebase structure from the SKF format.
"""

        # Generate guidelines using LLM
        guidelines = bedrock_client.generate_documentation(prompt)
        
        return guidelines
        
    except Exception as e:
        # Fallback to template-based guidelines if LLM fails
        return _generate_fallback_skf_guidelines(skf_content, project_name, stats)


def _generate_fallback_skf_guidelines(skf_content: str, project_name: str, stats: Dict[str, any]) -> str:
    """
    Generate basic SKF decoding guidelines without LLM (fallback).
    
    Args:
        skf_content: The SKF content to analyze
        project_name: Name of the project
        stats: Compression statistics
        
    Returns:
        Basic markdown formatted decoding guidelines
    """
    # Extract basic information from SKF content
    lines = skf_content.split('\n')
    
    # Extract header information
    source_docs = ""
    generation_timestamp = ""
    primary_namespace = ""
    
    for line in lines:
        if line.startswith("# SourceDocs:"):
            source_docs = line.replace("# SourceDocs:", "").strip()
        elif line.startswith("# GenerationTimestamp:"):
            generation_timestamp = line.replace("# GenerationTimestamp:", "").strip()
        elif line.startswith("# PrimaryNamespace:"):
            primary_namespace = line.replace("# PrimaryNamespace:", "").strip()
    
    # Count components
    definitions = [line for line in lines if line.startswith("D") and ":" in line]
    interactions = [line for line in lines if line.startswith("I") and ":" in line]
    usage_patterns = [line for line in lines if line.startswith("U_") and ":" in line]
    
    # Generate basic guidelines
    guidelines = f"""# SKF Format Decoding Guidelines

## Overview
This document provides decoding instructions for the Structured Knowledge Format (SKF) generated from the {project_name} documentation.

## Header Metadata
- **IntegratedKnowledgeManifest_SKF/1.4**: Format identifier and version
- **SourceDocs**: Original documentation sources ({source_docs})
- **GenerationTimestamp**: Creation timestamp ({generation_timestamp})
- **PrimaryNamespace**: Top-level package/namespace ({primary_namespace})

## Section Formats

### DEFINITIONS (Prefix: D)
Format: `Dxxx:Gxxx_Entity [DEF_TYP] [NAMESPACE "path"] [OPERATIONS {{...}}] [ATTRIBUTES {{...}}] ("Note")`

**Field Meanings:**
- **Dxxx**: Definition ID (D001, D002, etc.)
- **Gxxx_Entity**: Global ID and entity name
- **DEF_TYP**: 
  - `CompDef` = Component/Class Definition
  - `FuncDef` = Function Definition
- **NAMESPACE**: Relative path from PrimaryNamespace
- **OPERATIONS**: Method signatures
- **ATTRIBUTES**: Properties
- **Note**: Brief description

**Examples from the file:**
{chr(10).join(definitions[:3]) if definitions else "No definitions found"}

### INTERACTIONS (Prefix: I)
Format: `Ixxx:Source_Ref VERB Target_Ref ("Note")`

**Interaction Verbs:**
- **INVOKES**: Method/function calls
- **IMPORTS**: Module imports
- **USES_COMPONENT**: Component usage

**Examples from the file:**
{chr(10).join(interactions[:3]) if interactions else "No interactions found"}

### USAGE_PATTERNS (Prefix: U)
Format: 
```
U_Name:Title
U_Name.N:[Actor] ACTION (Target) -> [Result]
```

**Examples from the file:**
{chr(10).join(usage_patterns[:3]) if usage_patterns else "No usage patterns found"}

## Key Components Identified

### Statistics
- **Total Definitions**: {len(definitions)}
- **Total Interactions**: {len(interactions)}
- **Total Usage Patterns**: {len(usage_patterns)}

## Usage Instructions

1. **Finding Components**: Look for `CompDef` entries in the DEFINITIONS section
2. **Understanding Relationships**: Check INTERACTIONS section for dependencies
3. **Implementation Patterns**: Review USAGE_PATTERNS for common workflows
4. **Service Architecture**: The namespace structure shows the modular design

## Compression Statistics
- **Original Size**: {stats.get('original_size', 0):,} characters
- **SKF Size**: {stats.get('compressed_size', 0):,} characters  
- **Compression Ratio**: {stats.get('compression_ratio', 0):.1%} reduction in size
- **Token Efficiency**: Structured format enables faster AI parsing

This SKF format provides a machine-optimized representation of the {project_name} documentation, enabling efficient AI analysis and code generation while preserving essential architectural and implementation details.
"""
    
    return guidelines
