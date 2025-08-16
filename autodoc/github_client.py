import requests
import logging
import concurrent.futures
import time
import os
import json
import pickle
import sys
import getpass
from github import Github
from github import Auth
from .config import GITHUB_API_URL, MAX_COMMENTS_PER_PR
from .bedrock_client import BedrockClient

logger = logging.getLogger(__name__)

class GitHubClient:
    """Client for interacting with GitHub API"""
    
    def __init__(self, token=None):
        """
        Initialize GitHub client
        
        Args:
            token (str, optional): GitHub personal access token
        """
        # Get token from environment variable if not provided
        if token is None:
            self.token = os.environ.get("GITHUB_TOKEN", None)
        else:
            self.token = token
            
        if not self.token:
            raise ValueError("GitHub token not provided. Use --token parameter or set GITHUB_TOKEN environment variable.")
            
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}"
        }
        auth = Auth.Token(self.token)
        self.github = Github(auth=auth)
        self.bedrock_client = BedrockClient()  # Initialize Bedrock client once
        self.github_api_time = 0
        self.bedrock_api_time = 0
        self.llmtxt_generation_time = 0
    
    def get_pr_files(self, owner, repo, pr_number):
        """
        Get files changed in a PR
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            pr_number (int): Pull request number
            
        Returns:
            list: List of file information dictionaries
        """
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            logger.error(f"Error fetching PR files: {response.status_code}")
            if response.status_code == 403:
                logger.error("Rate limit exceeded or authentication failed. Please check your token.")
            return []
        
        return response.json()
    
    def get_pr_review_comments(self, owner, repo, pr_number):
        """
        Get review comments for a PR
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            pr_number (int): Pull request number
            
        Returns:
            list: List of processed comment dictionaries
        """
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            logger.error(f"Error fetching PR comments: {response.status_code}")
            if response.status_code == 403:
                logger.error("Rate limit exceeded or authentication failed. Please check your token.")
            return []
        
        comments = response.json()[:MAX_COMMENTS_PER_PR]  # Limit number of comments
        
        processed_comments = []
        for comment in comments:
            processed = {
                "reviewer_username": comment["user"]["login"],
                "code_block": comment["diff_hunk"],
                "review_comment": comment["body"],
                "created_at": comment["created_at"],
                "path": comment["path"],
                "line": comment.get("line"),
                "commit_id": comment.get("commit_id"),
                "file_extension": get_file_extension(comment.get("path", ""))
            }
            processed_comments.append(processed)
        
        return processed_comments
    
    def extract_pr_context(self, owner, repo, pr_number):
        """
        Extract comprehensive context about a PR
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            pr_number (int): Pull request number
            
        Returns:
            dict: PR context information
        """
        try:
            # Access repository through PyGithub
            repository = self.github.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            
            # Get basic PR information
            context = {
                "pr_number": pr_number,
                "title": pr.title,
                "description": pr.body,
                "author": pr.user.login,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "base_branch": pr.base.ref,
                "head_branch": pr.head.ref,
                "changed_files": pr.changed_files,
                "additions": pr.additions,
                "deletions": pr.deletions,
                "files": self.get_pr_files(owner, repo, pr_number),
                "review_comments": self.get_pr_review_comments(owner, repo, pr_number)
            }
            
            return context
        except Exception as e:
            logger.error(f"Error extracting PR context: {e}")
            if "403" in str(e):
                logger.error("Rate limit exceeded or authentication failed. Please check your token.")
            return None

    def _process_pr(self, owner, repo, pr_info):
        """Process a single PR and its comments"""
        try:
            start_time = time.time()
            # Get PR context including comments
            pr_context = self.extract_pr_context(owner, repo, pr_info['pr_number'])
            if pr_context:
                # Update the PR info with the full context
                pr_info.update(pr_context)
                end_time = time.time()
                self.github_api_time += (end_time - start_time)
                logger.info(f"Fetched comments for PR #{pr_info['pr_number']} in {end_time - start_time:.2f} seconds")
                return pr_info
        except Exception as e:
            logger.error(f"Error fetching comments for PR #{pr_info['pr_number']}: {str(e)}")
        return None
    
    def _classify_pr_comments(self, pr, quiet=False):
        """Classify comments for a single PR"""
        try:
            pr_analysis = {
                'pr_number': pr['pr_number'],
                'title': pr['title'],
                'comment_count': pr['comment_count'],
                'comment_analysis': []
            }
            
            if not quiet:
                print(f"\nProcessing PR #{pr['pr_number']}: {pr['title']}")
                print(f"Found {len(pr['review_comments'])} review comments (of {pr['comment_count']} total comments)")
            
            # Prepare all comments for batch classification
            comments_to_classify = []
            for comment in pr['review_comments']:
                if not comment.get('review_comment'):  # Skip empty comments
                    continue
                comment_text = f"File: {comment['path']}\n"
                comment_text += f"Comment: {comment['review_comment']}\n"
                if comment.get('code_block'):
                    comment_text += f"Code Block:\n{comment['code_block']}\n"
                comment_text += "---\n"
                comments_to_classify.append((comment, comment_text))
            
            if not comments_to_classify:
                if not quiet:
                    print("No comments to classify")
                return pr_analysis
            
            # Combine all comments into a single text
            combined_text = "\n".join(text for _, text in comments_to_classify)
            num_comments = len(comments_to_classify)
            
            # Get batch classification with timing
            start_time = time.time()
            if not quiet:
                print(f"Starting classification of all {num_comments} comments...")
            classifications = self.bedrock_client.classify_comments(combined_text, num_comments, quiet=quiet)
            end_time = time.time()
            self.bedrock_api_time += (end_time - start_time)
            if not quiet:
                print(f"Classified {num_comments} comments for PR #{pr['pr_number']} in {end_time - start_time:.2f} seconds")
            
            # Map classifications and inferences back to comments
            for idx, ((comment, _), classification) in enumerate(zip(comments_to_classify, classifications)):
                inference = ""
                if idx < len(self.bedrock_client.inferences):
                    inference = self.bedrock_client.inferences[idx]
                
                pr_analysis['comment_analysis'].append({
                    'file': comment['path'],
                    'comment': comment['review_comment'],
                    'classification': classification,
                    'inferred_comment': inference if classification == 'code_standards' else ""
                })
            
            if not quiet:
                print(f"Added {len(pr_analysis['comment_analysis'])} classified comments to analysis")
            return pr_analysis
        except Exception as e:
            print(f"Error analyzing PR #{pr['pr_number']}: {e}")
            return None
    
    def get_top_k_prs_by_comments(self, owner, repo, k=5):
        """
        Get top K merged PRs with highest number of comments
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            k (int): Number of top PRs to fetch (default: 5)
            
        Returns:
            list: List of PR information dictionaries sorted by comment count
        """
        try:
            start_time = time.time()
            print(f"Fetching PRs from {owner}/{repo}...")
            # Get repository through PyGithub
            repository = self.github.get_repo(f"{owner}/{repo}")
            
            # Use PyGithub search API with efficient query
            # is:pr is:merged repo:owner/repo state:closed
            query = f"repo:{owner}/{repo} is:pr is:merged state:closed"
            
            # Get PRs with pagination (100 PRs per page)
            # PyGithub automatically handles pagination
            # We'll fetch a reasonable number (300 most recent) for speed
            search_results = self.github.search_issues(query=query, sort='comments', order='desc')
            
            pr_count = 0
            prs_with_comments = []
            max_prs_to_check = min(300, search_results.totalCount)  # Limit to 300 or total count
            
            print(f"Found {search_results.totalCount} merged PRs, checking top {max_prs_to_check} by recent activity")
            
            # Process PRs from search results
            for issue in search_results[:max_prs_to_check]:
                try:
                    # Convert issue to PR
                    pr = repository.get_pull(issue.number)
                    
                    # Get basic PR info
                    pr_info = {
                        'pr_number': pr.number,
                        'title': pr.title,
                        'author': pr.user.login,
                        'created_at': pr.created_at.isoformat(),
                        'updated_at': pr.updated_at.isoformat(),
                        'description': pr.body or '',
                        'comment_count': pr.comments + pr.review_comments,  # Total comments
                    }
                    prs_with_comments.append(pr_info)
                    pr_count += 1
                    logger.info(f"Processed PR #{pr.number} with {pr_info['comment_count']} comments")
                
                    # If we have enough PRs with confirmed comment counts, we can stop early
                    if pr_count >= k * 2:  # Get 2x the requested number to ensure we have enough after sorting
                        break
                except Exception as e:
                    # Skip this PR and continue
                    logger.error(f"Error processing PR #{issue.number}: {str(e)}")
                    continue
                    
            if not prs_with_comments:
                logger.error("No merged PRs found")
                return None
            
            # Sort by total comment count in descending order (in case search API didn't sort perfectly)
            prs_with_comments.sort(key=lambda x: x['comment_count'], reverse=True)
            top_prs = prs_with_comments[:k]
            
            # Log PR finding completion time
            end_time = time.time()
            print(f"Found {len(prs_with_comments)} PRs in {end_time - start_time:.2f} seconds")
            print(f"Selected top {len(top_prs)} PRs with most comments")
            
            # Process PRs concurrently
            start_time = time.time()
            print("Fetching detailed information for selected PRs...")
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Create futures for PR processing
                futures = [executor.submit(self._process_pr, owner, repo, pr_info) 
                          for pr_info in top_prs]
                
                # Collect results as they complete
                processed_prs = []
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        processed_prs.append(result)
            
            end_time = time.time()
            print(f"PR detail fetching completed in {end_time - start_time:.2f} seconds")
            return processed_prs
            
        except Exception as e:
            logger.error(f"Error fetching top PRs: {str(e)}")
            return None
    
    def generate_llmtxt(self, owner, repo, limit=5, llmtxt_output='repo_llm.txt', quiet=False, resume=False, checkpoint_dir='.checkpoints'):
        """
        Generate LLM-friendly coding guidelines directly from PR comments
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            limit (int): Number of top PRs to analyze (default: 5)
            llmtxt_output (str): Output file for guidelines (default: repo_llm.txt)
            quiet (bool): Reduce verbose output
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Reset timing counters
            self.github_api_time = 0
            self.bedrock_api_time = 0
            self.llmtxt_generation_time = 0
            
            # If output filename is not specified, use more descriptive naming format
            if llmtxt_output is None or llmtxt_output == f"{repo}-llm.txt":
                llmtxt_output = f"{repo}-pr-comments-llm.txt"
            
            # Check if file already exists
            existing_content = ""
            existing_file = False
            if os.path.exists(llmtxt_output):
                try:
                    with open(llmtxt_output, 'r', encoding='utf-8') as f:
                        existing_content = f.read()
                    if existing_content.strip():
                        existing_file = True
                        if not quiet:
                            print(f"\nFound existing guidelines in {llmtxt_output} ({len(existing_content)} bytes)")
                except Exception as e:
                    logger.error(f"Error reading existing file: {e}")
                    existing_content = ""
                    existing_file = False
            else:
                if not quiet:
                    print(f"\nNo existing guidelines found. Creating new file {llmtxt_output}")
            
            if not quiet:
                print(f"Analyzing top {limit} PRs from {owner}/{repo} for coding guidelines...")
            # Get top PRs with comments
            # Create checkpoint directory if it doesn't exist
            checkpoint_path = os.path.join(checkpoint_dir, f"{owner}_{repo}_llmtxt.pkl")
            os.makedirs(checkpoint_dir, exist_ok=True)
            
            # Initialize variables for resuming
            all_comments = []
            code_standards_count = 0
            total_comments_count = 0
            top_prs = []
            processed_pr_ids = set()
            
            # Try to resume from checkpoint if requested
            if resume and os.path.exists(checkpoint_path):
                try:
                    if not quiet:
                        print(f"Resuming from checkpoint: {checkpoint_path}")
                    with open(checkpoint_path, 'rb') as f:
                        checkpoint_data = pickle.load(f)
                        all_comments = checkpoint_data.get('all_comments', [])
                        code_standards_count = checkpoint_data.get('code_standards_count', 0)
                        total_comments_count = checkpoint_data.get('total_comments_count', 0)
                        top_prs = checkpoint_data.get('top_prs', [])
                        processed_pr_ids = set(checkpoint_data.get('processed_pr_ids', []))
                    
                    if not quiet:
                        print(f"Resumed with {len(all_comments)} comments from {len(processed_pr_ids)} PRs")
                except Exception as e:
                    logger.error(f"Error loading checkpoint: {e}")
                    resume = False  # Fallback to regular processing
            
            # If not resuming or no checkpoint found, get PRs from scratch
            start_time = time.time()
            if not top_prs:  # Empty if not loaded from checkpoint
                top_prs = self.get_top_k_prs_by_comments(owner, repo, limit)
            
            if not top_prs:
                print("No PRs found")
                return False
            
            print(f"Found {len(top_prs)} PRs to analyze")
            
            # Process PRs concurrently - only those not yet processed
            unprocessed_prs = [pr for pr in top_prs if pr['pr_number'] not in processed_pr_ids]
            if not quiet and unprocessed_prs:
                print(f"Processing {len(unprocessed_prs)} remaining PRs...")
                
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Create futures for PR analysis
                futures = [executor.submit(self._classify_pr_comments, pr, quiet) 
                          for pr in unprocessed_prs]  # Only process unprocessed PRs
                
                # No progress bar needed
                
                # Process each PR and update the checkpoint after each one
                for future in concurrent.futures.as_completed(futures):
                    try:
                        result = future.result()
                        if result:
                            # Add PR to processed list
                            processed_pr_ids.add(result['pr_number'])
                            
                            # Extract comments
                            for analysis in result['comment_analysis']:
                                total_comments_count += 1
                                # Only include code_standards comments
                                if analysis['classification'] == 'code_standards':
                                    code_standards_count += 1
                                    comment_data = {
                                        'pr_number': result['pr_number'],
                                        'pr_title': result['title'],
                                        'file': analysis['file'],
                                        'comment': analysis['comment'],
                                        'classification': analysis['classification'],
                                    }
                                    if analysis.get('inferred_comment'):
                                        comment_data['inferred_comment'] = analysis['inferred_comment']
                                    all_comments.append(comment_data)
                            
                            # Update checkpoint after each PR is processed
                            try:
                                checkpoint_data = {
                                    'all_comments': all_comments,
                                    'code_standards_count': code_standards_count,
                                    'total_comments_count': total_comments_count,
                                    'top_prs': top_prs,
                                    'processed_pr_ids': list(processed_pr_ids)
                                }
                                with open(checkpoint_path, 'wb') as f:
                                    pickle.dump(checkpoint_data, f)
                                if not quiet:
                                    print(f"Checkpoint updated after processing PR #{result['pr_number']}")
                            except Exception as e:
                                logger.error(f"Error saving checkpoint: {e}")
                                
                    except Exception as e:
                        logger.error(f"Error processing PR: {e}")
                        # Error handling is done above
            
            if not quiet:
                print(f"Found {code_standards_count} code standards comments out of {total_comments_count} total comments")
            
            # Create final checkpoint with all processed data before LLM extraction
            try:
                final_checkpoint_data = {
                    'all_comments': all_comments,
                    'code_standards_count': code_standards_count,
                    'total_comments_count': total_comments_count,
                    'top_prs': top_prs,
                    'processed_pr_ids': list(processed_pr_ids),
                    'processing_stage': 'pr_analysis_complete'
                }
                with open(checkpoint_path, 'wb') as f:
                    pickle.dump(final_checkpoint_data, f)
                if not quiet:
                    print("PR analysis complete. Checkpoint saved.")
            except Exception as e:
                logger.error(f"Error saving final checkpoint: {e}")
                
            # Generate or update consolidated guidelines
            try:
                llmtxt_extraction_start = time.time()
                llmtxt_content = self.bedrock_client.generate_llmtxt_guidelines(all_comments, existing_content, quiet)
                llmtxt_extraction_end = time.time()
                self.llmtxt_generation_time = llmtxt_extraction_end - llmtxt_extraction_start
                
                # Update checkpoint to mark LLM extraction as complete
                try:
                    final_checkpoint_data['processing_stage'] = 'llm_extraction_complete'
                    with open(checkpoint_path, 'wb') as f:
                        pickle.dump(final_checkpoint_data, f)
                except Exception as e:
                    logger.error(f"Error updating checkpoint after LLM extraction: {e}")
                    
            except Exception as e:
                logger.error(f"Error during LLM extraction: {e}")
                print("An error occurred during LLM extraction. You can resume from the checkpoint.")
                return False
            
            # Check if content has actually changed and write file only if needed
            should_write = True
            if existing_file:
                # Perform basic similarity check
                content_changed = existing_content != llmtxt_content
                if not content_changed:
                    should_write = False
                    if not quiet:
                        print(f"No significant changes needed to guidelines in {llmtxt_output}")
            
            if should_write:
                # Write LLM-txt file
                if not quiet:
                    print(f"\nWriting guidelines to file...")
                
                # Write file
                with open(llmtxt_output, 'w', encoding='utf-8') as f:
                    f.write(llmtxt_content)
                
                if not quiet:
                    if existing_file:
                        print(f"Updated guidelines in {llmtxt_output}")
                    else:
                        print(f"Created new guidelines in {llmtxt_output}")
            
            end_time = time.time()
            if not quiet:
                print(f"LLM guideline extraction time: {self.llmtxt_generation_time:.2f} seconds")
                print(f"\nTotal GitHub API time: {self.github_api_time:.2f} seconds")
                print(f"Total Bedrock API time: {self.bedrock_api_time:.2f} seconds")
                print(f"Total processing time: {end_time - start_time:.2f} seconds")
                
                # Display cost information
                cost_report = self.bedrock_client.get_cost_report()
                print(f"\nBedrock API Usage:")
                print(f"Input tokens: {cost_report['input_tokens']}")
                print(f"Output tokens: {cost_report['output_tokens']}")
                print(f"Total tokens: {cost_report['total_tokens']}")
                print(f"Estimated cost: ${cost_report['total_cost']}")
                print(f"    Input cost: ${cost_report['cost_breakdown']['input_cost']}")
                print(f"    Output cost: ${cost_report['cost_breakdown']['output_cost']}")
                
                
            # Delete checkpoint if processing completed successfully
            try:
                if os.path.exists(checkpoint_path):
                    os.remove(checkpoint_path)
                    if not quiet:
                        print("Processing completed successfully. Checkpoint removed.")
            except Exception as e:
                logger.error(f"Error removing checkpoint: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error generating LLM-friendly guidelines: {e}")
            return False

    def classify_pr_comments(self, owner, repo, output_file='pr_analysis.txt', limit=5, quiet=False, resume=False, checkpoint_dir='.checkpoints'):
        """
        Classify PR comments using Bedrock and save analysis to file
        
        Args:
            owner (str): Repository owner/organization
            repo (str): Repository name
            output_file (str): Output file name (default: pr_analysis.txt)
            limit (int): Number of PRs to analyze (default: 5)
            quiet (bool): Reduce verbose output
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Reset timing counters
            self.github_api_time = 0
            self.bedrock_api_time = 0
            
            if not quiet:
                print(f"Analyzing top {limit} PRs from {owner}/{repo}...")
            # Get top PRs with comments
            top_prs = self.get_top_k_prs_by_comments(owner, repo, limit)
            
            if not top_prs:
                print("No PRs found")
                return False
            
            print(f"Found {len(top_prs)} PRs to analyze")
            
            # Process PRs concurrently
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Create futures for PR analysis
                futures = [executor.submit(self._classify_pr_comments, pr, quiet) 
                          for pr in top_prs]
                
                # Collect results as they complete
                all_comments = []
                pr_count = 0
                total_comments = 0
                total_review_comments = 0
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        pr_count += 1
                        total_comments += result['comment_count']
                        total_review_comments += len(result['comment_analysis'])
                        
                        if not quiet:
                            print(f"\nProcessing comments from PR #{result['pr_number']}")
                        
                        # Add all comments to the list
                        for analysis in result['comment_analysis']:
                            comment_entry = {}
                            comment_entry['pr_number'] = result['pr_number']
                            comment_entry['pr_title'] = result['title']
                            comment_entry.update(analysis)
                            all_comments.append(comment_entry)
                        
                        if not quiet:
                            print(f"Added {len(result['comment_analysis'])} comments from PR #{result['pr_number']}")
            
            if not quiet:
                print(f"\nWriting {len(all_comments)} total comments from {pr_count} PRs to file")
            
            # Format and write all comments to file
            with open(output_file, 'w', encoding='utf-8') as f:
                # Write header
                f.write(f"Code Review Comments Analysis\n")
                f.write(f"Repository: {owner}/{repo}\n")
                f.write(f"Total PRs analyzed: {pr_count}\n")
                f.write(f"Total comments: {total_comments} (analyzed {total_review_comments} review comments)\n\n")
                
                f.write("All Comments:\n\n")
                
                # Write each comment
                for comment in all_comments:
                    f.write(f"PR #{comment['pr_number']}: {comment['pr_title']}\n")
                    f.write(f"File: {comment['file']}\n")
                    f.write(f"Comment: {comment['comment']}\n")
                    f.write(f"Classification: {comment['classification']}\n")
                    if comment['classification'] == 'code_standards' and comment.get('inferred_comment'):
                        f.write(f"Inferred Standard: {comment['inferred_comment']}\n")
                    f.write("-" * 80 + "\n\n")
            
            # Log total timing
            if not quiet:
                print(f"\nTotal GitHub API time: {self.github_api_time:.2f} seconds")
                print(f"Total Bedrock API time: {self.bedrock_api_time:.2f} seconds")
                print(f"Total processing time: {self.github_api_time + self.bedrock_api_time:.2f} seconds")
                
                # Display cost information
                cost_report = self.bedrock_client.get_cost_report()
                print(f"\nBedrock API Usage:")
                print(f"Input tokens: {cost_report['input_tokens']}")
                print(f"Output tokens: {cost_report['output_tokens']}")
                print(f"Total tokens: {cost_report['total_tokens']}")
                print(f"Estimated cost: ${cost_report['total_cost']}")
                print(f"    Input cost: ${cost_report['cost_breakdown']['input_cost']}")
                print(f"    Output cost: ${cost_report['cost_breakdown']['output_cost']}")
                
            
            # Generate LLM-friendly text file if requested
            if generate_llmtxt:
                # Generate output filename based on repo name if not provided
                if llmtxt_output is None:
                    llmtxt_output = f"{repo}-llm.txt"
                    
                if not quiet:
                    print(f"\nGenerating LLM-friendly guidelines in {llmtxt_output}...")
                start_time = time.time()
                
                # Extract code standards comments from all PRs for processing
                all_comments = []
                code_standards_count = 0
                total_comments_count = 0
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        for analysis in result['comment_analysis']:
                            total_comments_count += 1
                            # Only include code_standards comments
                            if analysis['classification'] == 'code_standards':
                                code_standards_count += 1
                                comment_data = {
                                    'pr_number': result['pr_number'],
                                    'pr_title': result['title'],
                                    'file': analysis['file'],
                                    'comment': analysis['comment'],
                                    'classification': analysis['classification'],
                                }
                                if analysis.get('inferred_comment'):
                                    comment_data['inferred_comment'] = analysis['inferred_comment']
                                all_comments.append(comment_data)
                
                if not quiet:
                    print(f"Found {code_standards_count} code standards comments out of {total_comments_count} total comments")
                
                # Generate consolidated guidelines
                llmtxt_extraction_start = time.time()
                llmtxt_content = self.bedrock_client.generate_llmtxt_guidelines(all_comments, "", quiet)
                llmtxt_extraction_end = time.time()
                self.llmtxt_generation_time = llmtxt_extraction_end - llmtxt_extraction_start
                
                # Write LLM-txt file
                with open(llmtxt_output, 'w', encoding='utf-8') as f:
                    f.write(llmtxt_content)
                
                end_time = time.time()
                if not quiet:
                    print(f"LLM guideline extraction time: {self.llmtxt_generation_time:.2f} seconds")
                    print(f"Total LLM-txt generation time: {end_time - start_time:.2f} seconds")
                    
                    # Display cost information
                    cost_report = self.bedrock_client.get_cost_report()
                    print(f"\nBedrock API Usage:")
                    print(f"Input tokens: {cost_report['input_tokens']}")
                    print(f"Output tokens: {cost_report['output_tokens']}")
                    print(f"Total tokens: {cost_report['total_tokens']}")
                    print(f"Estimated cost: ${cost_report['total_cost']}")
                    print(f"    Input cost: ${cost_report['cost_breakdown']['input_cost']}")
                    print(f"    Output cost: ${cost_report['cost_breakdown']['output_cost']}")
                    
                
                # Remove the analysis file if not needed
                if not keep_analysis and os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                        if not quiet:
                            print(f"Removed temporary analysis file {output_file}")
                    except Exception as e:
                        logger.error(f"Failed to remove analysis file: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error classifying PR comments: {e}")
            return False

def get_file_extension(file_path):
    """Extract file extension from path"""
    if not file_path or '.' not in file_path:
        return ""
    return file_path.split('.')[-1]
