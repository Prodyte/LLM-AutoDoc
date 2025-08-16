#!/usr/bin/env python3
import logging
import os
from src.bedrock_client import BedrockClient
from src.github_client import GitHubClient

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_bedrock_client():
    """Test the Bedrock client functionality"""
    try:
        # Initialize Bedrock client
        bedrock_client = BedrockClient()
        logging.info("Successfully initialized Bedrock client")

        # Test comment classification
        code_snippet = """
        def calculate_total(items):
            total = 0
            for item in items:
                total += item.price
            return total
        """
        comment = "Consider using sum() with a generator expression for better readability"
        
        classification = bedrock_client.classify_comment(code_snippet, comment)
        logging.info(f"Comment classification result: {classification}")

        # Test review comment generation
        similar_reviews = [
            {
                'metadata': {
                    'reviewer_username': 'expert1',
                    'review_comment': 'Use list comprehension for better readability'
                },
                'similarity': 0.85
            }
        ]
        
        generated_comment = bedrock_client.generate_review_comment(code_snippet, similar_reviews)
        logging.info(f"Generated review comment: {generated_comment}")

    except Exception as e:
        logging.error(f"Error testing Bedrock client: {e}")

def test_github_client():
    """Test the GitHub client functionality"""
    try:
        # Initialize GitHub client with token from environment variable
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            logging.warning("GITHUB_TOKEN environment variable not set")
            return

        github_client = GitHubClient(token=github_token)
        logging.info("Successfully initialized GitHub client")

        # Test PR context extraction
        owner = "example-org"  # Replace with actual org/repo
        repo = "example-repo"
        pr_number = 123  # Replace with actual PR number

        pr_context = github_client.extract_pr_context(owner, repo, pr_number)
        if pr_context:
            logging.info(f"Successfully extracted PR context for PR #{pr_number}")
            logging.info(f"PR Title: {pr_context['title']}")
            logging.info(f"Author: {pr_context['author']}")
            logging.info(f"Changed files: {pr_context['changed_files']}")
        else:
            logging.error("Failed to extract PR context")

    except Exception as e:
        logging.error(f"Error testing GitHub client: {e}")

def main():
    """Main function to run all tests"""
    logging.info("Starting client tests...")
    
    # Test Bedrock client
    logging.info("\n=== Testing Bedrock Client ===")
    test_bedrock_client()
    
    # Test GitHub client
    logging.info("\n=== Testing GitHub Client ===")
    test_github_client()
    
    logging.info("\nClient tests completed")

if __name__ == "__main__":
    main() 