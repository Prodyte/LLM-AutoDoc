"""
Repository manager for handling GitHub operations including cloning and repository management.
"""
import os
import subprocess
import tempfile
import shutil
from typing import Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class RepoManager:
    """Manages repository operations including cloning and cleanup."""
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize repository manager.
        
        Args:
            temp_dir: Optional temporary directory path. If None, uses system temp.
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.cloned_repos = []  # Track cloned repos for cleanup
    
    def parse_github_url(self, url: str) -> Tuple[str, str]:
        """
        Parse GitHub URL to extract owner and repository name.
        
        Args:
            url: GitHub repository URL
            
        Returns:
            Tuple of (owner, repo_name)
            
        Raises:
            ValueError: If URL format is invalid
        """
        try:
            # Handle both https://github.com/owner/repo and owner/repo formats
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
    
    def clone_repository(self, repo_url: str, target_dir: Optional[str] = None, 
                        shallow: bool = True, quiet: bool = False) -> str:
        """
        Clone a GitHub repository to a local directory.
        
        Args:
            repo_url: GitHub repository URL
            target_dir: Target directory path. If None, creates temp directory.
            shallow: Whether to perform shallow clone (faster, less history)
            quiet: Whether to suppress git output
            
        Returns:
            str: Path to the cloned repository
            
        Raises:
            RuntimeError: If cloning fails
        """
        try:
            owner, repo_name = self.parse_github_url(repo_url)
            
            # Determine target directory
            if target_dir is None:
                target_dir = os.path.join(self.temp_dir, f"{owner}_{repo_name}")
            
            # Remove existing directory if it exists
            if os.path.exists(target_dir):
                if not quiet:
                    print(f"Removing existing directory: {target_dir}")
                shutil.rmtree(target_dir)
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(target_dir), exist_ok=True)
            
            # Build git clone command
            git_cmd = ['git', 'clone']
            
            if shallow:
                git_cmd.extend(['--depth', '1'])
            
            if quiet:
                git_cmd.append('--quiet')
            
            # Ensure we're using HTTPS URL
            if not repo_url.startswith('http'):
                repo_url = f'https://github.com/{repo_url}'
            
            git_cmd.extend([repo_url, target_dir])
            
            if not quiet:
                print(f"Target directory: {target_dir}")
            
            # Execute git clone
            result = subprocess.run(
                git_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown git error"
                raise RuntimeError(f"Git clone failed: {error_msg}")
            
            # Verify the directory was created and contains files
            if not os.path.exists(target_dir) or not os.listdir(target_dir):
                raise RuntimeError("Repository was not cloned successfully")
            
            # Track cloned repo for cleanup
            self.cloned_repos.append(target_dir)
            
            if not quiet:
                print(f"Successfully cloned repository to: {target_dir}")
            
            return target_dir
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Repository cloning timed out (5 minutes)")
        except Exception as e:
            raise RuntimeError(f"Failed to clone repository: {e}")
    
    def is_git_repository(self, path: str) -> bool:
        """
        Check if a directory is a git repository.
        
        Args:
            path: Directory path to check
            
        Returns:
            bool: True if it's a git repository
        """
        try:
            git_dir = os.path.join(path, '.git')
            return os.path.exists(git_dir)
        except Exception:
            return False
    
    def get_repository_info(self, repo_path: str) -> dict:
        """
        Get basic information about a repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            dict: Repository information
        """
        info = {
            'path': repo_path,
            'exists': os.path.exists(repo_path),
            'is_git_repo': False,
            'remote_url': None,
            'branch': None,
            'file_count': 0
        }
        
        if not info['exists']:
            return info
        
        info['is_git_repo'] = self.is_git_repository(repo_path)
        
        # Count files
        try:
            file_count = 0
            for root, dirs, files in os.walk(repo_path):
                # Skip .git directory
                if '.git' in dirs:
                    dirs.remove('.git')
                file_count += len(files)
            info['file_count'] = file_count
        except Exception:
            pass
        
        # Get git info if it's a git repo
        if info['is_git_repo']:
            try:
                # Get remote URL
                result = subprocess.run(
                    ['git', 'remote', 'get-url', 'origin'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    info['remote_url'] = result.stdout.strip()
                
                # Get current branch
                result = subprocess.run(
                    ['git', 'branch', '--show-current'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    info['branch'] = result.stdout.strip()
                    
            except Exception as e:
                logger.debug(f"Failed to get git info: {e}")
        
        return info
    
    def cleanup_cloned_repos(self, quiet: bool = False):
        """
        Clean up all cloned repositories.
        
        Args:
            quiet: Whether to suppress output
        """
        for repo_path in self.cloned_repos:
            try:
                if os.path.exists(repo_path):
                    if not quiet:
                        print(f"Cleaning up: {repo_path}")
                    shutil.rmtree(repo_path)
            except Exception as e:
                if not quiet:
                    print(f"Warning: Failed to cleanup {repo_path}: {e}")
        
        self.cloned_repos.clear()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup_cloned_repos(quiet=True)


def clone_repo_for_analysis(repo_url: str, quiet: bool = False) -> Tuple[str, RepoManager]:
    """
    Convenience function to clone a repository for analysis.
    
    Args:
        repo_url: GitHub repository URL
        quiet: Whether to suppress output
        
    Returns:
        Tuple of (repo_path, repo_manager)
    """
    repo_manager = RepoManager()
    repo_path = repo_manager.clone_repository(repo_url, quiet=quiet)
    return repo_path, repo_manager


def validate_github_url(url: str) -> bool:
    """
    Validate if a URL is a valid GitHub repository URL.
    
    Args:
        url: URL to validate
        
    Returns:
        bool: True if valid GitHub URL
    """
    try:
        if not url.startswith('http'):
            url = f'https://github.com/{url}'
        
        parsed = urlparse(url)
        
        # Check if it's github.com
        if parsed.netloc.lower() not in ['github.com', 'www.github.com']:
            return False
        
        # Check if path has at least owner/repo
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) < 2:
            return False
        
        # Basic validation of owner and repo names
        owner, repo = path_parts[0], path_parts[1]
        if not owner or not repo:
            return False
        
        # Remove .git suffix for validation
        if repo.endswith('.git'):
            repo = repo[:-4]
        
        # Basic character validation (GitHub allows alphanumeric, hyphens, underscores)
        import re
        if not re.match(r'^[a-zA-Z0-9._-]+$', owner) or not re.match(r'^[a-zA-Z0-9._-]+$', repo):
            return False
        
        return True
        
    except Exception:
        return False
