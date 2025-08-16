"""
Unified CLI combining PR comments mining and documentation generation functionality.
"""
import argparse
import sys
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from .github_client import GitHubClient
from .repo_manager import RepoManager, validate_github_url
from .unified_config import UnifiedConfig
from .compression import compress_markdown_to_skf
from .file_discovery import discover_source_files
from .js_parser import parse_js_ts_file, convert_to_file_info as js_convert_to_file_info
from .dependency_graph import build_dependency_graph
from .documentation_assembly import assemble_documentation
from .setup_environment import setup_complete_environment, run_diagnostics


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse GitHub repository URL to extract owner and repo"""
    try:
        # Handle both https://github.com/owner/repo and owner/repo
        if not url.startswith('http'):
            url = f'https://github.com/{url}'
        
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) < 2:
            raise ValueError("Invalid repository URL format")
        
        owner = path_parts[0]
        repo = path_parts[1]
        
        # Remove .git suffix if present
        if repo.endswith('.git'):
            repo = repo[:-4]
        
        return owner, repo
    except Exception as e:
        raise ValueError(f"Failed to parse repository URL: {e}")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse GitHub PR URL to extract owner, repo, and PR number"""
    try:
        # Handle both https://github.com/owner/repo/pull/123 and owner/repo/pull/123
        if not url.startswith('http'):
            url = f'https://github.com/{url}'
        
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) < 4 or path_parts[2] != 'pull':
            raise ValueError("Invalid PR URL format")
        
        owner = path_parts[0]
        repo = path_parts[1]
        pr_number = int(path_parts[3])
        
        return owner, repo, pr_number
    except Exception as e:
        raise ValueError(f"Failed to parse PR URL: {e}")


def generate_documentation_for_repo(repo_path: str, output_file: Optional[str] = None, 
                                   compress: bool = False) -> str:
    """
    Generate documentation for a local repository.
    
    Args:
        repo_path: Path to the repository
        output_file: Optional output file name
        compress: Whether to also generate compressed version
        
    Returns:
        Path to the generated documentation file
    """
    print(f"Generating documentation for: {repo_path}")
    print(f"Supported file types: {', '.join(UnifiedConfig.SUPPORTED_EXTENSIONS)}")
    
    # Step 1: Discover source files
    print("\n1. Discovering source files...")
    try:
        source_files = discover_source_files(repo_path)
        print(f"   Found {len(source_files)} source files")
        
        if not source_files:
            print("   No supported source files found in the repository.")
            return None
        
        # Group files by type for reporting
        file_types = {}
        for file_path in source_files:
            ext = Path(file_path).suffix
            file_types[ext] = file_types.get(ext, 0) + 1
        
        for ext, count in file_types.items():
            print(f"   - {ext}: {count} files")
            
    except Exception as e:
        raise RuntimeError(f"Failed to discover source files: {e}")
    
    # Step 2: Parse source files
    print("\n2. Parsing source files...")
    all_file_info = []
    
    for i, file_path in enumerate(source_files, 1):
        relative_path = os.path.relpath(file_path, repo_path)
        print(f"   [{i}/{len(source_files)}] Parsing {relative_path}")
        
        try:
            file_info = parse_source_file(file_path)
            if file_info:
                all_file_info.append(file_info)
        except Exception as e:
            print(f"      Warning: Failed to parse {relative_path}: {e}")
            continue
    
    print(f"   Successfully parsed {len(all_file_info)} files")
    
    if not all_file_info:
        print("   No files could be parsed successfully.")
        return None
    
    # Step 3: Build dependency graph
    print("\n3. Building dependency graph...")
    try:
        dependency_graph = build_dependency_graph(all_file_info)
        print(f"   Graph created with {dependency_graph.number_of_nodes()} nodes and {dependency_graph.number_of_edges()} edges")
    except Exception as e:
        raise RuntimeError(f"Failed to build dependency graph: {e}")
    
    # Step 4: Generate documentation
    print("\n4. Generating documentation with AWS Bedrock...")
    try:
        # Set output file if specified
        if output_file:
            original_output = UnifiedConfig.DEFAULT_DOC_OUTPUT
            UnifiedConfig.DEFAULT_DOC_OUTPUT = output_file
        
        assemble_documentation(repo_path, dependency_graph, all_file_info)
        
        # Restore original output setting
        if output_file:
            UnifiedConfig.DEFAULT_DOC_OUTPUT = original_output
        
        doc_path = os.path.join(repo_path, output_file or UnifiedConfig.DEFAULT_DOC_OUTPUT)
        
        # Generate compressed version if requested
        if compress:
            print("\n5. Generating compressed documentation...")
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    md_content = f.read()
                
                compressed_content, stats = compress_markdown_to_skf(md_content, Path(repo_path).name)
                
                compressed_path = doc_path.replace('.md', UnifiedConfig.DEFAULT_COMPRESSED_SUFFIX)
                with open(compressed_path, 'w', encoding='utf-8') as f:
                    f.write(compressed_content)
                
                print(f"   Compressed documentation saved to: {compressed_path}")
                print(f"   Original size: {stats['original_size']:,} characters")
                print(f"   Compressed size: {stats['compressed_size']:,} characters")
                print(f"   Compression ratio: {stats['compression_ratio']:.1%}")
                
                # Generate SKF decoding guidelines
                print("\n6. Generating SKF decoding guidelines...")
                try:
                    from .compression import generate_skf_decoding_guidelines
                    guidelines = generate_skf_decoding_guidelines(
                        compressed_content, 
                        Path(repo_path).name, 
                        stats
                    )
                    
                    guidelines_path = doc_path.replace('.md', '_skf_decoder.md')
                    with open(guidelines_path, 'w', encoding='utf-8') as f:
                        f.write(guidelines)
                    
                    print(f"   SKF decoding guidelines saved to: {guidelines_path}")
                    
                except Exception as e:
                    print(f"   Warning: Failed to generate SKF decoding guidelines: {e}")
                
            except Exception as e:
                print(f"   Warning: Failed to generate compressed documentation: {e}")
        
        return doc_path
        
    except Exception as e:
        raise RuntimeError(f"Failed to generate documentation: {e}")


def parse_source_file(file_path: str):
    """Parse a single source file based on its extension."""
    file_extension = Path(file_path).suffix.lower()
    
    if file_extension in ['.js', '.jsx', '.ts', '.tsx']:
        try:
            parsed_data = parse_js_ts_file(file_path)
            return js_convert_to_file_info(file_path, parsed_data)
        except Exception as e:
            raise RuntimeError(f"JavaScript/TypeScript parsing error: {e}")
    else:
        raise RuntimeError(f"Unsupported file extension: {file_extension}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Unified GitHub Repository Analysis Tool - PR Comments Mining & Documentation Generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup environment
  etc-repo setup
  
  # Run diagnostics
  etc-repo setup --diagnostics
  
  # Generate PR comments guidelines
  etc-repo generate https://github.com/owner/repo -k 10
  
  # Generate documentation for local repo
  etc-repo document /path/to/repo
  
  # Generate documentation for remote repo (clones automatically)
  etc-repo document https://github.com/owner/repo --compress
  
  # Get top PRs by comment count
  etc-repo top https://github.com/owner/repo -k 5
  
  # Analyze specific PR
  etc-repo pr https://github.com/owner/repo/pull/123

Environment Variables:
  GITHUB_TOKEN            GitHub personal access token
  AWS_PROFILE             AWS profile to use (default: qa)
  AWS_REGION              AWS region (default: us-east-1)
  BEDROCK_MODEL_ID        Bedrock model ID
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Common arguments for all commands
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--token', help='GitHub personal access token')
    parent_parser.add_argument('--quiet', action='store_true', help='Reduce verbose output')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', parents=[parent_parser], help='Setup environment dependencies and validate configuration')
    setup_parser.add_argument('--diagnostics', action='store_true', help='Run diagnostics instead of setup')
    
    # PR info command
    pr_parser = subparsers.add_parser('pr', parents=[parent_parser], help='Fetch PR information')
    pr_parser.add_argument('pr_url', help='GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)')
    pr_parser.add_argument('--format', choices=['json', 'text'], default='text',
                          help='Output format (default: text)')
    
    # Top PRs command
    top_parser = subparsers.add_parser('top', parents=[parent_parser], help='Fetch top PRs by comment count')
    top_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    top_parser.add_argument('-k', type=int, default=5, help='Number of top PRs to fetch (default: 5)')
    top_parser.add_argument('--format', choices=['json', 'text'], default='text',
                          help='Output format (default: text)')
    
    # Generate LLM-txt command (PR comments analysis)
    generate_parser = subparsers.add_parser('generate', parents=[parent_parser], 
                                          help='Generate LLM-friendly coding guidelines from PR comments')
    generate_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    generate_parser.add_argument('-k', type=int, default=5, help='Number of top PRs to analyze (default: 5)')
    generate_parser.add_argument('--output', default=None, help='Output file name (auto-generated from repo name if not provided)')
    generate_parser.add_argument('--resume', action='store_true', help='Resume from checkpoint if processing was interrupted')
    generate_parser.add_argument('--checkpoint-dir', default='.checkpoints', help='Directory for checkpoint files (default: .checkpoints)')
    
    # Document command (documentation generation)
    doc_parser = subparsers.add_parser('document', parents=[parent_parser], 
                                     help='Generate comprehensive documentation for a repository')
    doc_parser.add_argument('repo_path', help='Repository path (local directory or GitHub URL)')
    doc_parser.add_argument('--output', default=None, help='Output documentation file name (default: documentation.md)')
    doc_parser.add_argument('--compress', action='store_true', help='Also generate compressed SKF format documentation')
    doc_parser.add_argument('--keep-clone', action='store_true', help='Keep cloned repository after documentation generation')
    
    # Classify PR comments command
    classify_parser = subparsers.add_parser('classify', parents=[parent_parser], help='Classify PR comments using Bedrock')
    classify_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    classify_parser.add_argument('-k', type=int, default=5, help='Number of top PRs to analyze (default: 5)')
    classify_parser.add_argument('--output', default='pr_analysis.txt', help='Output file name for analysis (default: pr_analysis.txt)')
    classify_parser.add_argument('--resume', action='store_true', help='Resume from checkpoint if processing was interrupted')
    classify_parser.add_argument('--checkpoint-dir', default='.checkpoints', help='Directory for checkpoint files (default: .checkpoints)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        # Handle setup command
        if args.command == 'setup':
            if args.diagnostics:
                run_diagnostics()
            else:
                success = setup_complete_environment()
                if not success:
                    sys.exit(1)
            return
        
        # Handle documentation command
        elif args.command == 'document':
            repo_path = args.repo_path
            
            # Check if it's a GitHub URL or local path
            if validate_github_url(repo_path):
                # It's a GitHub URL, clone it
                print(f"Cloning repository: {repo_path}")
                with RepoManager() as repo_manager:
                    cloned_path = repo_manager.clone_repository(repo_path, quiet=args.quiet)
                    doc_file = generate_documentation_for_repo(
                        cloned_path, 
                        args.output, 
                        args.compress
                    )
                    
                    if doc_file and args.keep_clone:
                        print(f"Repository cloned to: {cloned_path}")
                        print(f"Documentation generated: {doc_file}")
                    elif doc_file:
                        # Copy documentation to current directory
                        import shutil
                        local_doc_file = os.path.basename(doc_file)
                        shutil.copy2(doc_file, local_doc_file)
                        print(f"Documentation copied to: {local_doc_file}")
                        
                        if args.compress:
                            compressed_file = doc_file.replace('.md', UnifiedConfig.DEFAULT_COMPRESSED_SUFFIX)
                            if os.path.exists(compressed_file):
                                local_compressed_file = os.path.basename(compressed_file)
                                shutil.copy2(compressed_file, local_compressed_file)
                                print(f"Compressed documentation copied to: {local_compressed_file}")
                            
                            # Also copy SKF decoder guidelines if they exist
                            decoder_file = doc_file.replace('.md', '_skf_decoder.md')
                            if os.path.exists(decoder_file):
                                local_decoder_file = os.path.basename(decoder_file)
                                shutil.copy2(decoder_file, local_decoder_file)
                                print(f"SKF decoder guidelines copied to: {local_decoder_file}")
            else:
                # It's a local path
                if not os.path.exists(repo_path):
                    print(f"Error: Repository path does not exist: {repo_path}")
                    sys.exit(1)
                
                doc_file = generate_documentation_for_repo(
                    repo_path, 
                    args.output, 
                    args.compress
                )
                
                if doc_file:
                    print(f"Documentation generated: {doc_file}")
        
        # Handle PR-related commands
        else:
            client = GitHubClient(token=args.token)
            
            if args.command == 'pr':
                owner, repo, pr_number = parse_pr_url(args.pr_url)
                context = client.extract_pr_context(owner, repo, pr_number)
                
                if not context:
                    print("Failed to fetch PR context", file=sys.stderr)
                    sys.exit(1)
                
                if args.format == 'json':
                    import json
                    print(json.dumps(context, indent=2))
                else:
                    # Text format output
                    print(f"\nPR #{context['pr_number']}: {context['title']}")
                    print(f"Author: {context['author']}")
                    print(f"Created: {context['created_at']}")
                    print(f"Updated: {context['updated_at']}")
                    print(f"\nDescription:\n{context['description']}\n")
                    
                    print("\nReview Comments:")
                    for comment in context['review_comments']:
                        print(f"\n{comment['reviewer_username']} ({comment['created_at']}):")
                        print(f"File: {comment['path']}")
                        print(f"Comment: {comment['review_comment']}")
                        if comment['code_block']:
                            print("\nCode Block:")
                            print(comment['code_block'])
                        print("-" * 80)
            
            elif args.command == 'top':
                owner, repo = parse_repo_url(args.repo_url)
                print(f"Fetching top {args.k} PRs from {owner}/{repo}...")
                top_prs = client.get_top_k_prs_by_comments(owner, repo, args.k)
                
                if not top_prs:
                    print("No PRs found or failed to fetch PRs", file=sys.stderr)
                    sys.exit(1)
                
                if args.format == 'json':
                    import json
                    print(json.dumps(top_prs, indent=2))
                else:
                    print(f"\nTop {len(top_prs)} PRs by comment count for {owner}/{repo}:")
                    for context in top_prs:
                        print(f"\nPR #{context['pr_number']}: {context['title']}")
                        print(f"Author: {context['author']}")
                        print(f"Created: {context['created_at']}")
                        print(f"Updated: {context['updated_at']}")
                        print(f"Total Comments: {context['comment_count']}")
                        print(f"\nDescription:\n{context['description']}\n")
                        print("=" * 80)
            
            elif args.command == 'generate':
                owner, repo = parse_repo_url(args.repo_url)
                print(f"Generating coding guidelines from {owner}/{repo} PRs...")
                
                # Derive filename from repo name if not specified
                output_file = args.output or f"{repo}-pr-comments-llm.txt"
                success = client.generate_llmtxt(owner, repo, args.k, output_file, args.quiet,
                                              resume=args.resume, checkpoint_dir=args.checkpoint_dir)
                
                if success:
                    print(f"Successfully generated coding guidelines: {output_file}")
                else:
                    print("Failed to generate coding guidelines", file=sys.stderr)
                    sys.exit(1)
            
            elif args.command == 'classify':
                owner, repo = parse_repo_url(args.repo_url)
                print(f"Analyzing top {args.k} PRs from {owner}/{repo}...")
                
                success = client.classify_pr_comments(owner, repo, args.output, args.k, quiet=args.quiet,
                                                   resume=args.resume, checkpoint_dir=args.checkpoint_dir)
                
                if success:
                    print(f"Successfully generated analysis file: {args.output}")
                else:
                    print("Failed to classify PR comments", file=sys.stderr)
                    sys.exit(1)
    
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
