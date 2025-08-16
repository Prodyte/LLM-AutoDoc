import boto3
import json
import logging
from botocore.config import Config
from .config import AWS_PROFILE, AWS_REGION, BEDROCK_MODEL_ID, MAX_TOKENS_PER_CALL

logger = logging.getLogger(__name__)

class BedrockClient:
    """Client for interacting with AWS Bedrock API for Claude models with cost tracking"""
    
    def __init__(self):
        """Initialize Bedrock client with QA profile"""
        try:
            session = boto3.Session(profile_name=AWS_PROFILE)
            config = Config(
                region_name=AWS_REGION,
                retries={
                    'max_attempts': 3,
                    'mode': 'standard'
                },
                connect_timeout=30,  # 30 seconds connection timeout
                read_timeout=300     # 5 minutes read timeout
            )
            self.client = session.client('bedrock-runtime', config=config)
            self.inferences = []  # Store inferences from classifications
            
            # Add token and cost tracking
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_cost = 0.0
            
            logger.info(f"Initialized Bedrock client with profile {AWS_PROFILE}")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            raise
    
    def tracked_invoke_model(self, modelId, body, track_cost=True):
        """
        Invoke Bedrock model with cost tracking
        
        Args:
            modelId (str): The model ID to use
            body (str): Request body JSON string
            track_cost (bool): Whether to track token usage and cost
            
        Returns:
            dict: Bedrock API response
        """
        # Call the Bedrock API
        response = self.client.invoke_model(modelId=modelId, body=body)
        
        # Extract usage data if tracking is enabled
        if track_cost:
            response_body = json.loads(response.get('body').read())
            usage = response_body.get('usage', {})
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            
            # Update token counters
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            
            # Calculate and update cost
            cost = self.calculate_cost(modelId, input_tokens, output_tokens)
            self.total_cost += cost
            
            # Re-encode the response body so it can be read again by caller
            import io
            response['body'] = io.BytesIO(json.dumps(response_body).encode())
            
        return response
        
    def calculate_cost(self, modelId, input_tokens, output_tokens):
        """
        Calculate cost for a specific model and token usage
        
        Args:
            modelId (str): The model ID used
            input_tokens (int): Number of input tokens
            output_tokens (int): Number of output tokens
            
        Returns:
            float: Cost in USD
        """
        # Claude 3 Sonnet pricing (update with current prices if needed)
        if "claude-3-sonnet" in modelId.lower():
            input_rate = 0.003 / 1000  # $0.003 per 1K input tokens
            output_rate = 0.015 / 1000  # $0.015 per 1K output tokens
        # Claude 3 Haiku
        elif "claude-3-haiku" in modelId.lower():
            input_rate = 0.00125 / 1000  # $0.00125 per 1K input tokens
            output_rate = 0.00625 / 1000  # $0.00625 per 1K output tokens
        # Claude 3 Opus
        elif "claude-3-opus" in modelId.lower():
            input_rate = 0.015 / 1000  # $0.015 per 1K input tokens
            output_rate = 0.075 / 1000  # $0.075 per 1K output tokens
        # Default/fallback pricing
        else:
            input_rate = 0.003 / 1000
            output_rate = 0.015 / 1000
        
        input_cost = input_tokens * input_rate
        output_cost = output_tokens * output_rate
        
        return input_cost + output_cost
    
    def generate_embeddings(self, texts):
        """
        Generate embeddings for a list of text using Claude
        
        Args:
            texts (list): List of text strings to embed
            
        Returns:
            list: List of embeddings
        """
        # Note: For MVP using sentence-transformers instead of Bedrock embeddings
        # This is a placeholder for future implementation
        raise NotImplementedError("Direct Bedrock embeddings not implemented in MVP. "
                                 "Using sentence-transformers instead.")
    
    def generate_llmtxt_guidelines(self, all_comments, existing_content="", quiet=False):
        """
        Generate concise, consolidated coding guidelines from PR comments
        
        Args:
            all_comments (list): List of PR comments with their classifications and context
            existing_content (str): Existing guidelines content to build upon if any
            quiet (bool): Whether to suppress progress information
            
        Returns:
            str: Generated guidelines in LLM-friendly format
        """
        from .config import LLMTXT_GENERATION_PROMPT, LLMTXT_UPDATE_PROMPT
        
        # Format comments as context
        comments_text = ""
        # If there are many comments, we need to be more selective
        if len(all_comments) > 30:
            # Group comments by file for better organization
            file_comments = {}
            for comment_data in all_comments:
                file = comment_data.get('file', 'Unknown file')
                comment = comment_data.get('comment', '')
                inferred = comment_data.get('inferred_comment', '')
                if file not in file_comments:
                    file_comments[file] = []
                file_comments[file].append((comment, inferred))
            
            # For each file, select at most 5 comments
            for file, file_data in file_comments.items():
                comments_text += f"File: {file}\n"
                # Take most informative comments (prioritize ones with inferences)
                selected = sorted(file_data, key=lambda x: len(x[1]), reverse=True)[:5]
                for i, (comment, inferred) in enumerate(selected, 1):
                    comments_text += f"Comment {i}: {comment}\n"
                    if inferred:
                        comments_text += f"Inferred Standard: {inferred}\n"
                comments_text += "\n"
        else:
            # Process all comments if there aren't too many
            for comment_data in all_comments:
                file = comment_data.get('file', 'Unknown file')
                comment = comment_data.get('comment', '')
                classification = comment_data.get('classification', 'general')
                inferred = comment_data.get('inferred_comment', '')
                comments_text += f"File: {file}\nComment: {comment}\nClassification: {classification}\n"
                if inferred:
                    comments_text += f"Inferred: {inferred}\n"
                comments_text += "\n"
        
        # Use different prompt based on whether we have existing content
        if existing_content.strip():
            # Handle large existing content more efficiently
            content_length = len(existing_content)
            if content_length > 20000:  # If content is very large
                if not quiet:
                    print(f"Large existing content detected ({content_length} chars). Optimizing...")
                # Extract the most important sections: TOC and first 10000 chars + last 5000 chars
                import re
                # Try to extract table of contents
                toc_match = re.search(r'## Table of Contents.*?(?=##\s+\w+|$)', existing_content, re.DOTALL)
                toc_section = toc_match.group(0) if toc_match else ""
                # Get beginning and end of content
                start_content = existing_content[:10000]
                end_content = existing_content[-5000:] if len(existing_content) > 5000 else ""
                # Create optimized content
                optimized_content = f"{toc_section}\n\n{start_content}\n\n...\n[Content truncated for efficiency]\n\n{end_content}"
                prompt = LLMTXT_UPDATE_PROMPT.format(existing_content=optimized_content, comments_text=comments_text)
            else:
                prompt = LLMTXT_UPDATE_PROMPT.format(existing_content=existing_content, comments_text=comments_text)
            prompt_type = "Updating existing guidelines"
        else:
            prompt = LLMTXT_GENERATION_PROMPT.format(comments_text=comments_text)
            prompt_type = "Generating new guidelines"
        
        try:
            # Log operation type
            if not quiet:
                print(f"\n{prompt_type} with LLM...")
            # Format the request for Claude
            # Use a smaller token limit to speed up the generation
            max_tokens = min(10000, MAX_TOKENS_PER_CALL)
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": 0.2,  # Lower temperature for more consistent outputs
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
                
            response = self.tracked_invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=body
            )
            
                
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                result = content[0].get('text', '').strip()
                
                    
                return result
            
            logger.warning(f"Unexpected response structure: {response_body}")
            return "Unable to generate coding guidelines."
            
        except Exception as e:
            logger.error(f"Error generating coding guidelines: {e}")
            return f"Error generating coding guidelines: {str(e)}"
            
    def classify_comment(self, code_snippet, comment):
        """
        Classify a comment into one of three categories
        
        Args:
            code_snippet (str): Code context for the comment
            comment (str): The comment text
            
        Returns:
            str: 'code_standards', 'discussions', or 'general'
        """
        from .config import COMMENT_CLASSIFICATION_PROMPT

        
        prompt = COMMENT_CLASSIFICATION_PROMPT.format(
            code_snippet=code_snippet,
            comment=comment
        )
        
        try:
            # Format the request for Claude
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 5,  # Minimal tokens for classification
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            response = self.tracked_invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=body
            )
            
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                result = content[0].get('text', '').strip().lower()
                if 'code_standards' in result:
                    return 'code_standards'
                elif 'discussions' in result:
                    return 'discussions'
                else:
                    return 'general'
            
            logger.warning(f"Unexpected response structure: {response_body}")
            return 'general'  # Default to general if unclear
            
        except Exception as e:
            logger.error(f"Error classifying comment: {e}")
            return 'general'  # Default to general on errors
    
    def generate_review_comment(self, code_snippet, similar_reviews):
        """
        Generate a code review comment based on similar past reviews
        
        Args:
            code_snippet (str): Code to review
            similar_reviews (list): List of similar past reviews
            
        Returns:
            str: Generated review comment
        """
        from .config import COMMENT_GENERATION_PROMPT
        
        # Format similar reviews as context
        reviews_text = ""
        for idx, review in enumerate(similar_reviews, 1):
            reviewer = review['metadata'].get('reviewer_username', 'Unknown reviewer')
            comment = review['metadata'].get('review_comment', '')
            similarity = review['similarity']
            reviews_text += f"Review {idx} (similarity: {similarity:.2f}) from {reviewer}:\n"
            reviews_text += f"\"{comment}\"\n\n"
            
            # Limit to 3-5 examples to keep context size reasonable
            if idx >= 5:
                break
        
        prompt = COMMENT_GENERATION_PROMPT.format(
            code_snippet=code_snippet,
            similar_reviews=reviews_text
        )
        
        try:
            # Format the request for Claude
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
            response = self.tracked_invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=body
            )
            
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                return content[0].get('text', '').strip()
            
            logger.warning(f"Unexpected response structure: {response_body}")
            return "Unable to generate review comment."
            
        except Exception as e:
            logger.error(f"Error generating review comment: {e}")
            return f"Error generating review comment: {str(e)}"

    def get_cost_report(self):
        """
        Get a report of token usage and costs
        
        Returns:
            dict: Token usage and cost information
        """
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "total_cost": round(self.total_cost, 4),
            "cost_breakdown": {
                "input_cost": round(self.calculate_cost(BEDROCK_MODEL_ID, self.input_tokens, 0), 4),
                "output_cost": round(self.calculate_cost(BEDROCK_MODEL_ID, 0, self.output_tokens), 4)
            }
        }
    
    def classify_comments(self, combined_text, num_comments, quiet=False):
        """
        Classify multiple comments in a single call
        
        Args:
            combined_text (str): Combined text of all comments with their context
            num_comments (int): Number of comments to classify
            quiet (bool): Whether to show progress bar
            
        Returns:
            list: List of classifications ('code_standards', 'discussions', or 'general')
        """
        from .config import COMMENT_CLASSIFICATION_PROMPT
        
        structured_prompt = f"""
{COMMENT_CLASSIFICATION_PROMPT}

I have {num_comments} comments to classify. Please provide exactly {num_comments} responses.

For each comment, provide the classification on one line. If it's a code_standards comment, add the inference on the next line.
Then leave a blank line before the next comment's classification.

Code snippet context:
Multiple code snippets in comments below

Comments to classify:
{combined_text}

Please provide exactly {num_comments} responses with the format described above:
"""
        
        try:
            # Log operation
            if not quiet:
                print(f"\nClassifying {num_comments} comments with LLM...")
            
            # Format the request for Claude
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,  # Reduced for faster classification
                "messages": [
                    {
                        "role": "user",
                        "content": structured_prompt
                    }
                ]
            })
            
            
            # Apply timeout to the request
            response = self.tracked_invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=body
            )
            
                
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                result = content[0].get('text', '').strip()
                # Split the result into individual responses
                classifications = []
                inferences = []
                
                # Process each comment's response
                responses = result.split('\n\n')
                for response in responses:
                    if not response.strip():  # Skip empty responses
                        continue
                    
                    lines = response.strip().split('\n')
                    classification_line = lines[0].lower().strip()
                    
                    # Extract classification
                    if 'code_standards' in classification_line:
                        classifications.append('code_standards')
                        # Extract inference if present (for code_standards)
                        if len(lines) > 1 and lines[1].strip():
                            inferences.append(lines[1].strip())
                        else:
                            inferences.append('')  # Empty inference
                    elif 'discussions' in classification_line:
                        classifications.append('discussions')
                        inferences.append('')  # No inference for discussions
                    else:
                        classifications.append('general')
                        inferences.append('')  # No inference for general
                
                # Store inferences as a class variable to be accessed by github_client
                self.inferences = inferences
                
                # Ensure we return exactly num_comments classifications
                if len(classifications) < num_comments:
                    # Pad with 'general' if not enough classifications returned
                    classifications.extend(['general'] * (num_comments - len(classifications)))
                elif len(classifications) > num_comments:
                    # Truncate if too many classifications returned
                    classifications = classifications[:num_comments]
                
                    
                return classifications
            
            logger.warning(f"Unexpected response structure: {response_body}")
            return ['general'] * num_comments  # Default to general
            
        except Exception as e:
            logger.error(f"Error classifying comments: {e}")
            return ['general'] * num_comments  # Default to general