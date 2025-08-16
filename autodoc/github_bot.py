import logging
import os
from github import Github
from .comment_processor import CommentProcessor

logger = logging.getLogger(__name__)

class GitHubBot:
    """Bot for automatically adding code review comments to GitHub PRs"""
    
    def __init__(self, token=None, confidence_threshold=0.75):
        """
        Initialize GitHub Bot
        
        Args:
            token (str, optional): GitHub personal access token
            confidence_threshold (float): Minimum confidence for posting comments
        """
        self.token = token
        self.github = Github(token) if token else Github()
        self.processor = CommentProcessor()
        self.confidence_threshold = confidence_threshold
        logger.info("Initialized GitHub bot")
    
    def review_pr(self, owner, repo, pr_number, add_comments=False):
        """
        Review a PR and optionally add comments
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            pr_number (int): Pull request number
            add_comments (bool): Whether to add comments to the PR
            
        Returns:
            dict: Summary of review results
        """
        try:
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            
            logger.info(f"Reviewing PR #{pr_number} in {owner}/{repo}")
            
            # Get files from PR
            suggestions_by_file = {}
            total_suggestions = 0
            
            for file in pr.get_files():
                if not file.patch:
                    continue
                
                # Get suggestions for this file
                file_suggestions = self.processor.generate_suggestions(
                    file.patch, file.filename
                )
                
                # Filter low confidence suggestions
                high_confidence = [
                    s for s in file_suggestions 
                    if s['confidence'] >= self.confidence_threshold
                ]
                
                if high_confidence:
                    suggestions_by_file[file.filename] = high_confidence
                    total_suggestions += len(high_confidence)
            
            # Add comments to PR if requested
            comments_added = 0
            if add_comments and total_suggestions > 0:
                comments_added = self._add_comments_to_pr(pr, suggestions_by_file)
            
            return {
                "pr_number": pr_number,
                "total_suggestions": total_suggestions,
                "files_with_suggestions": len(suggestions_by_file),
                "comments_added": comments_added
            }
                
        except Exception as e:
            logger.error(f"Error reviewing PR: {e}")
            return {
                "error": str(e),
                "pr_number": pr_number
            }
    
    def _add_comments_to_pr(self, pr, suggestions_by_file):
        """
        Add comments to a PR based on suggestions
        
        Args:
            pr: PyGithub PR object
            suggestions_by_file: Dict of filename -> suggestions
            
        Returns:
            int: Number of comments added
        """
        comments_added = 0
        
        try:
            # Get the latest commit
            latest_commit = list(pr.get_commits())[-1]
            
            for filename, suggestions in suggestions_by_file.items():
                # Get file from latest commit
                try:
                    file_content = pr.get_files().get_contents(filename, ref=latest_commit.sha)
                    
                    for suggestion in suggestions:
                        # Format comment body
                        body = (
                            f"**Code Review Bot Suggestion** (Confidence: {suggestion['confidence']:.2f})\n\n"
                            f"{suggestion['comment']}\n\n"
                            f"_Based on a similar comment by @{suggestion['reviewer']}_"
                        )
                        
                        # Try to add comment
                        pr.create_review_comment(
                            body=body,
                            commit_id=latest_commit.sha,
                            path=filename,
                            # Note: line numbers are approximate without better context
                            # In a full implementation, we would use better line matching
                            position=1  
                        )
                        
                        comments_added += 1
                        logger.info(f"Added comment to {filename} in PR #{pr.number}")
                        
                except Exception as e:
                    logger.error(f"Error adding comment to file {filename}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error adding comments to PR: {e}")
        
        return comments_added