import argparse
import sys
from urllib.parse import urlparse
from .github_client import GitHubClient

def parse_pr_url(url):
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

def parse_repo_url(url):
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
        
        return owner, repo
    except Exception as e:
        raise ValueError(f"Failed to parse repository URL: {e}")

def main():
    parser = argparse.ArgumentParser(description='GitHub Repository Tools')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Common arguments for all commands
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--token', help='GitHub personal access token')
    
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
    
    # LLM text generation command
    llm_parser = subparsers.add_parser('llmtxtgen', parents=[parent_parser], help='Generate LLM text file from PR comments')
    llm_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    llm_parser.add_argument('--output', default='llms.txt', help='Output file name (default: llms.txt)')
    llm_parser.add_argument('-k', type=int, default=10, help='Number of PRs to include (default: 10)')
    
    # Classify PR comments command
    classify_parser = subparsers.add_parser('classify', parents=[parent_parser], help='Classify PR comments using Bedrock')
    classify_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    classify_parser.add_argument('-k', type=int, default=5, help='Number of top PRs to analyze (default: 5, max PRs to process)')
    classify_parser.add_argument('--output', default='pr_analysis.txt', help='Output file name for analysis (default: pr_analysis.txt)')
    classify_parser.add_argument('--quiet', action='store_true', help='Reduce verbose output')
    classify_parser.add_argument('--llmtxt', action='store_true', help='Generate LLM-friendly text file with consolidated guidelines')
    classify_parser.add_argument('--llmtxt-output', default=None, help='Output file for LLM-friendly text (auto-generated from repo name if not provided)')
    classify_parser.add_argument('--resume', action='store_true', help='Resume from checkpoint if processing was interrupted')
    classify_parser.add_argument('--checkpoint-dir', default='.checkpoints', help='Directory for checkpoint files (default: .checkpoints)')
    
    # Generate LLM-txt command
    generate_parser = subparsers.add_parser('generate', parents=[parent_parser], help='Generate LLM-friendly coding guidelines from PR comments')
    generate_parser.add_argument('repo_url', help='GitHub repository URL (e.g., https://github.com/owner/repo)')
    generate_parser.add_argument('-k', type=int, default=5, help='Number of top PRs to analyze (default: 5, max PRs to process)')
    generate_parser.add_argument('--output', default=None, help='Output file name (auto-generated from repo name if not provided)')
    generate_parser.add_argument('--quiet', action='store_true', help='Reduce verbose output')
    generate_parser.add_argument('--resume', action='store_true', help='Resume from checkpoint if processing was interrupted')
    generate_parser.add_argument('--checkpoint-dir', default='.checkpoints', help='Directory for checkpoint files (default: .checkpoints)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
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
        
        elif args.command == 'llmtxtgen':
            owner, repo = parse_repo_url(args.repo_url)
            print(f"Generating llms.txt with top {args.k} PRs from {owner}/{repo}...")
            success = client.generate_llm_text(owner, repo, args.output, args.k)
            
            if not success:
                print("Failed to generate LLM text file", file=sys.stderr)
                sys.exit(1)
            
            print(f"Successfully generated LLM text file: {args.output}")
            
        elif args.command == 'generate':
            owner, repo = parse_repo_url(args.repo_url)
            print(f"Generating coding guidelines from {owner}/{repo} PRs...")
            
            # Derive filename from repo name if not specified
            output_file = args.output or f"{repo}-pr-comments-llm.txt"
            success = client.generate_llmtxt(owner, repo, args.k, output_file, args.quiet,
                                          resume=args.resume, checkpoint_dir=args.checkpoint_dir)
            
        elif args.command == 'classify':
            owner, repo = parse_repo_url(args.repo_url)
            print(f"Analyzing top {args.k} PRs from {owner}/{repo}...")
            
            # If llmtxt is requested, go directly to that mode
            if args.llmtxt:
                # Derive filename from repo name if not specified
                llmtxt_output = args.llmtxt_output or f"{repo}-pr-comments-llm.txt"
                success = client.generate_llmtxt(owner, repo, args.k, llmtxt_output, args.quiet, 
                                              resume=args.resume, checkpoint_dir=args.checkpoint_dir)
            else:
                # Regular classify mode with PR analysis
                success = client.classify_pr_comments(owner, repo, args.output, args.k, quiet=args.quiet,
                                                   resume=args.resume, checkpoint_dir=args.checkpoint_dir)
            
            if not success:
                print("Failed to classify PR comments", file=sys.stderr)
                sys.exit(1)
            
            # Only print success message for analysis file if not in llmtxt-only mode
            if not args.llmtxt:
                print(f"Successfully generated analysis file: {args.output}")
            
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main() 