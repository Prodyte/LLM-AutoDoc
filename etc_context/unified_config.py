"""
Unified configuration settings for the combined PR comments miner and documentation tool.
"""
import os
from typing import Dict, Any


class UnifiedConfig:
    """Unified configuration class combining both tools' settings."""
    
    # AWS Configuration (common to both tools)
    AWS_PROFILE = os.getenv('AWS_PROFILE', 'qa')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
    BEDROCK_TEMPERATURE = float(os.getenv('BEDROCK_TEMPERATURE', '0.1'))
    BEDROCK_MAX_TOKENS = int(os.getenv('BEDROCK_MAX_TOKENS', '4000'))
    BEDROCK_TOP_P = float(os.getenv('BEDROCK_TOP_P', '0.9'))
    MAX_TOKENS_PER_CALL = int(os.getenv('MAX_TOKENS_PER_CALL', '40000'))
    
    # GitHub Configuration
    GITHUB_API_URL = "https://api.github.com"
    MAX_COMMENTS_PER_PR = 100
    AUTO_TRAIN_ON_PROCESS = True
    
    # Database Configuration (for PR comments)
    EMBEDDING_DIMENSION = 384  # Default for all-MiniLM-L6-v2
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                          "data", "embeddings")
    
    # Documentation Tool Configuration
    SUPPORTED_EXTENSIONS = ['.js', '.jsx', '.ts', '.tsx']
    IGNORE_DIRECTORIES = {
        'node_modules', '.git', 'target', 'dist', 'build', 
        '.next', '.nuxt', 'coverage', '.nyc_output', 
        'bower_components', 'vendor', '.vscode', '.idea'
    }
    
    # Output Configuration
    DEFAULT_DOC_OUTPUT = 'documentation.md'
    DEFAULT_PR_OUTPUT = 'pr_analysis.txt'
    OUTPUT_FILE = 'documentation.md'
    MAX_CONTEXT_LENGTH = 8000
    
    # Rate limiting settings
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 1.0  # seconds
    MAX_RETRY_DELAY = 60.0  # seconds
    
    # Compression settings
    DEFAULT_COMPRESSED_SUFFIX = '.skf.txt'
    
    @classmethod
    def get_bedrock_config(cls) -> Dict[str, Any]:
        """Get Bedrock configuration as a dictionary."""
        return {
            'region': cls.AWS_REGION,
            'model_id': cls.BEDROCK_MODEL_ID,
            'temperature': cls.BEDROCK_TEMPERATURE,
            'max_tokens': cls.BEDROCK_MAX_TOKENS,
            'top_p': cls.BEDROCK_TOP_P
        }
    
    @classmethod
    def validate_aws_credentials(cls) -> bool:
        """Validate that AWS credentials are available."""
        return (
            os.getenv('AWS_ACCESS_KEY_ID') is not None or
            os.path.exists(os.path.expanduser('~/.aws/credentials')) or
            os.getenv('AWS_PROFILE') is not None
        )
    
    # Model prompts (from PR comments tool)
    LLMTXT_GENERATION_PROMPT = """
Create concise yet comprehensive coding guidelines from these PR comments with this structure:

# [Repository Name] Coding Guidelines
## Table of Contents
1. [Code Standards](#code-standards)
2. [Asynchronous Programming](#asynchronous-programming)
3. [Error Handling](#error-handling)
4. [Naming Conventions](#naming-conventions)
5. [Performance Considerations](#performance-considerations)
6. [Code Organization](#code-organization)

## Code Standards
### Formatting and Style
- Use bullet points for each guideline
- Format code examples with backticks like `example_code`

### Best Practices
- Use bullet points with specific, actionable advice
- Refer to specific methods, classes or patterns when relevant

## Asynchronous Programming
- Use bullet points with concrete examples
- Reference specific libraries and functions (e.g., `Future`, `AsyncStream`)

## Error Handling
- Use bullet points focused on specific patterns
- Include common error handling methods like `Option`, pattern matching

## Naming Conventions
- Use bullet points with clear examples
- Reference actual naming patterns used in the codebase

## Performance Considerations
- Use bullet points with performance impact specified
- Include specific performance optimization techniques

## Code Organization
- Use bullet points with concrete structural advice
- Include principles like Single Responsibility, dependency injection

### High-Priority Issues
- List exactly 5 most important guidelines
- Focus on critical issues with specific examples

Make each point concise and focused on one concept.
Eliminate redundancy between guidelines.
Reference specific code patterns and examples from the codebase.
Preserve important technical references for development context.

Comments:
{comments_text}
"""

    LLMTXT_UPDATE_PROMPT = """
Existing guidelines document:

{existing_content}

New PR comments to integrate:

{comments_text}

Update the guidelines efficiently:
1. Maintain the exact structure and formatting (title, TOC, sections)
2. Only add new guidelines not already covered
3. Keep the same table of contents format with numbered links
4. Focus on extracting unique insights from new comments
5. Make each point concise and focused on one specific concept
6. Make guidelines specific and actionable, not general
7. Eliminate redundancy between guidelines
8. Reference specific code patterns and examples from the codebase
9. Preserve important technical references and methods
10. Ensure the High-Priority Issues section contains exactly 5 most important items

Output only the updated guidelines document, no explanations.
"""

    COMMENT_CLASSIFICATION_PROMPT = """
Analyze the following comment from a GitHub pull request review.
Determine if this is:
1. 'code_standards' - specific feedback about code quality, patterns, conventions, best practices, naming conventions, code organization, safe coding practices, formatting issues, stylistic guidelines, code structure suggestions, or any comments about improving code implementation
2. 'discussions' - questions, clarifications, architectural decisions, design discussions, or comments seeking information
3. 'general' - other types of comments not fitting the above categories

Code snippet context:
{code_snippet}

Comment:
{comment}

Your response must have exactly two parts:
1. Classification: Respond with only 'code_standards', 'discussions', or 'general'
2. Inference: ONLY if the classification is 'code_standards', on a new line add an inference about the underlying coding standard or best practice in 1-2 concise sentences. Extract the core principle, explain why it matters, and make it reusable for similar situations.

For example:
code_standards
Functions that don't depend on instance variables should be defined in the companion object to improve code organization and reduce unnecessary instantiation.

Or if not a code standard:
discussions
"""

    COMMENT_GENERATION_PROMPT = """
You are a helpful code review assistant that provides constructive feedback on code. 
You have access to a collection of previous code review comments from expert reviewers.

I'll provide you with:
1. New code snippet that needs review
2. Similar past code reviews that might be relevant

Your task is to generate a concise, constructive code review comment that:
- Focuses on the specific issues in the code
- Is polite and helpful
- Explains why the issue matters
- Provides a specific suggestion for improvement if possible

New code snippet:
```
{code_snippet}
```

Context from similar past reviews:
{similar_reviews}

Generate a helpful code review comment for this code:
"""
