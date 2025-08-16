# ETC Context - Unified GitHub Repository Analysis Tool

A powerful CLI tool that combines PR comments mining and automated documentation generation for GitHub repositories. Extract coding guidelines from PR reviews and generate comprehensive documentation using AWS Bedrock LLM.

## Features

### 🔍 PR Comments Mining
- Extract and analyze PR review comments from GitHub repositories
- Generate LLM-friendly coding guidelines from expert reviews
- Classify comments by type (code standards, discussions, general)
- Support for checkpoint-based processing with resume capability

### 📚 Documentation Generation
- Automatically generate comprehensive documentation for codebases
- Support for JavaScript, TypeScript, JSX, and TSX files
- Dependency graph analysis and visualization
- AWS Bedrock LLM-powered intelligent documentation
- Compressed SKF format for efficient AI parsing

### 🚀 Repository Management
- Automatic GitHub repository cloning
- Support for both local and remote repositories
- Intelligent file discovery and parsing
- Clean temporary file management

## Installation

### Prerequisites
- Python 3.8+
- Node.js and npm (for JavaScript/TypeScript parsing)
- AWS CLI configured with Bedrock access
- Git

### Install from Source
```bash
git clone <repository-url>
cd LLM-AutoDoc
pip install -e .
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

## Configuration

### Environment Variables
```bash
# GitHub Access
export GITHUB_TOKEN="your_github_token"

# AWS Configuration
export AWS_PROFILE="qa"  # or your preferred profile
export AWS_REGION="us-east-1"
export BEDROCK_MODEL_ID="us.anthropic.claude-3-5-sonnet-20241022-v2:0"

# Optional: Custom settings
export BEDROCK_TEMPERATURE="0.1"
export BEDROCK_MAX_TOKENS="4000"
```

### AWS Bedrock Setup
1. Configure AWS credentials: `aws configure`
2. Request access to Claude models in AWS Bedrock console
3. Ensure your region supports Bedrock (us-east-1 recommended)

## Usage

The unified tool provides several commands for different use cases:

### Environment Setup

#### Setup Dependencies
Set up all required dependencies and validate configuration:
```bash
# Complete environment setup
etc-repo setup

# Run diagnostics to check current setup
etc-repo setup --diagnostics
```

### PR Comments Analysis

#### Generate Coding Guidelines
Extract coding guidelines from PR review comments:
```bash
# Generate guidelines from top 10 PRs
etc-repo generate https://github.com/owner/repo -k 10

# Custom output file
etc-repo generate https://github.com/owner/repo -k 5 --output my-guidelines.txt

# Resume interrupted processing
etc-repo generate https://github.com/owner/repo -k 10 --resume
```

#### Analyze Top PRs
Get repositories with most review activity:
```bash
# Top 5 PRs by comment count
etc-repo top https://github.com/owner/repo -k 5

# JSON output format
etc-repo top https://github.com/owner/repo -k 10 --format json
```

#### Analyze Specific PR
Get detailed information about a specific PR:
```bash
etc-repo pr https://github.com/owner/repo/pull/123
```

#### Classify PR Comments
Analyze and classify PR comments:
```bash
etc-repo classify https://github.com/owner/repo -k 5 --output analysis.txt
```

### Documentation Generation

#### Generate Documentation for Local Repository
```bash
# Basic documentation generation
etc-repo document /path/to/local/repo

# With custom output file
etc-repo document /path/to/local/repo --output my-docs.md

# Generate both full and compressed versions
etc-repo document /path/to/local/repo --compress
```

#### Generate Documentation for Remote Repository
```bash
# Clone and generate documentation
etc-repo document https://github.com/owner/repo

# Keep cloned repository after processing
etc-repo document https://github.com/owner/repo --keep-clone

# Generate compressed documentation
etc-repo document https://github.com/owner/repo --compress
```

## Command Reference

### Global Options
- `--token`: GitHub personal access token
- `--quiet`: Reduce verbose output

### Commands

#### `generate` - PR Comments Guidelines
Generate LLM-friendly coding guidelines from PR comments.

**Arguments:**
- `repo_url`: GitHub repository URL
- `-k`: Number of top PRs to analyze (default: 5)
- `--output`: Output file name (auto-generated if not provided)
- `--resume`: Resume from checkpoint
- `--checkpoint-dir`: Checkpoint directory (default: .checkpoints)

#### `document` - Documentation Generation
Generate comprehensive documentation for a repository.

**Arguments:**
- `repo_path`: Repository path (local directory or GitHub URL)
- `--output`: Output documentation file name (default: documentation.md)
- `--compress`: Also generate compressed SKF format
- `--keep-clone`: Keep cloned repository after processing

#### `top` - Top PRs Analysis
Fetch top PRs by comment count.

**Arguments:**
- `repo_url`: GitHub repository URL
- `-k`: Number of top PRs to fetch (default: 5)
- `--format`: Output format (text/json, default: text)

#### `pr` - Single PR Analysis
Fetch detailed information about a specific PR.

**Arguments:**
- `pr_url`: GitHub PR URL
- `--format`: Output format (text/json, default: text)

#### `classify` - Comment Classification
Classify PR comments using Bedrock.

**Arguments:**
- `repo_url`: GitHub repository URL
- `-k`: Number of top PRs to analyze (default: 5)
- `--output`: Output file name (default: pr_analysis.txt)
- `--resume`: Resume from checkpoint
- `--checkpoint-dir`: Checkpoint directory

## Examples

### Complete Workflow Example
```bash
# 1. Generate coding guidelines from PR comments
etc-repo generate https://github.com/facebook/react -k 15 --output react-guidelines.txt

# 2. Generate comprehensive documentation
etc-repo document https://github.com/facebook/react --compress --output react-docs.md

# 3. Analyze top PRs for insights
etc-repo top https://github.com/facebook/react -k 10 --format json > react-top-prs.json
```

### Local Development Workflow
```bash
# Generate documentation for current project
etc-repo document . --compress

# Analyze your team's PR patterns
etc-repo generate https://github.com/yourorg/yourproject -k 20
```

## File Formats

### Documentation Output
- **Markdown (.md)**: Human-readable comprehensive documentation
- **SKF (.skf.txt)**: Compressed format optimized for AI/LLM consumption

### PR Analysis Output
- **Text (.txt)**: LLM-friendly coding guidelines
- **JSON**: Structured data for programmatic use

## Supported Languages

### Documentation Generation
- JavaScript (.js)
- TypeScript (.ts)
- JSX (.jsx)
- TSX (.tsx)

### Parser Requirements
- **JavaScript/TypeScript**: Node.js and npm

## Troubleshooting

### Common Issues

#### AWS Bedrock Access
```bash
# Check AWS configuration
aws sts get-caller-identity

# Verify Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

#### GitHub Rate Limits
```bash
# Use personal access token
export GITHUB_TOKEN="your_token_here"

# Check rate limit status
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit
```

#### Parser Setup
```bash
# Setup Node.js dependencies
cd LLM-AutoDoc/parsers && npm install

```

### Error Messages

- **"AWS credentials not found"**: Configure AWS CLI or set environment variables
- **"Cannot connect to AWS Bedrock"**: Check region and model access permissions
- **"Node.js parser not set up"**: Run `npm install` in parsers directory
- **"Repository not found"**: Verify repository URL and access permissions
