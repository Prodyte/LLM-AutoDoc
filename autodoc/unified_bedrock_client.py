"""
Unified AWS Bedrock client combining PR comments analysis and documentation generation.
"""
import boto3
import json
import time
import logging
from typing import Dict, Any, Optional, List
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, BotoCoreError
from .unified_config import UnifiedConfig

logger = logging.getLogger(__name__)


class UnifiedBedrockClient:
    """Unified Bedrock client for both PR analysis and documentation generation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize unified Bedrock client.
        
        Args:
            config: Optional configuration dictionary. If None, uses UnifiedConfig defaults.
        """
        self.config = config or UnifiedConfig.get_bedrock_config()
        self.region = self.config['region']
        self.model_id = self.config['model_id']
        
        try:
            # Initialize with session and profile support
            if UnifiedConfig.AWS_PROFILE and UnifiedConfig.AWS_PROFILE != 'default':
                session = boto3.Session(profile_name=UnifiedConfig.AWS_PROFILE)
            else:
                session = boto3.Session()
                
            boto_config = BotoConfig(
                region_name=self.region,
                retries={
                    'max_attempts': UnifiedConfig.MAX_RETRIES,
                    'mode': 'standard'
                },
                connect_timeout=30,
                read_timeout=300
            )
            
            self.client = session.client('bedrock-runtime', config=boto_config)
            
            # Token and cost tracking
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_cost = 0.0
            self.total_requests = 0
            self.inferences = []  # Store inferences from classifications
            
            logger.info(f"Initialized unified Bedrock client with profile {UnifiedConfig.AWS_PROFILE}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            raise RuntimeError(f"Failed to initialize Bedrock client: {e}")
    
    def tracked_invoke_model(self, modelId: str, body: str, track_cost: bool = True) -> Dict[str, Any]:
        """
        Invoke Bedrock model with cost tracking and retry logic.
        
        Args:
            modelId: The model ID to use
            body: Request body JSON string
            track_cost: Whether to track token usage and cost
            
        Returns:
            dict: Bedrock API response
        """
        for attempt in range(UnifiedConfig.MAX_RETRIES):
            try:
                response = self.client.invoke_model(modelId=modelId, body=body)
                self.total_requests += 1
                
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
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                
                if error_code == 'ThrottlingException' and attempt < UnifiedConfig.MAX_RETRIES - 1:
                    delay = min(
                        UnifiedConfig.INITIAL_RETRY_DELAY * (2 ** attempt),
                        UnifiedConfig.MAX_RETRY_DELAY
                    )
                    print(f"Rate limited. Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    raise RuntimeError(f"Bedrock API error: {e}")
                    
            except BotoCoreError as e:
                if attempt < UnifiedConfig.MAX_RETRIES - 1:
                    delay = UnifiedConfig.INITIAL_RETRY_DELAY * (2 ** attempt)
                    print(f"Network error. Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    raise RuntimeError(f"Network error: {e}")
        
        raise RuntimeError(f"Failed to invoke model after {UnifiedConfig.MAX_RETRIES} attempts")
    
    def calculate_cost(self, modelId: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for a specific model and token usage.
        
        Args:
            modelId: The model ID used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            float: Cost in USD
        """
        # Claude 3.5 Sonnet pricing (update with current prices if needed)
        if "claude-3-5-sonnet" in modelId.lower() or "claude-3.5-sonnet" in modelId.lower():
            input_rate = 0.003 / 1000  # $0.003 per 1K input tokens
            output_rate = 0.015 / 1000  # $0.015 per 1K output tokens
        # Claude 3 Sonnet
        elif "claude-3-sonnet" in modelId.lower():
            input_rate = 0.003 / 1000
            output_rate = 0.015 / 1000
        # Claude 3 Haiku
        elif "claude-3-haiku" in modelId.lower():
            input_rate = 0.00125 / 1000
            output_rate = 0.00625 / 1000
        # Claude 3 Opus
        elif "claude-3-opus" in modelId.lower():
            input_rate = 0.015 / 1000
            output_rate = 0.075 / 1000
        # Default/fallback pricing
        else:
            input_rate = 0.003 / 1000
            output_rate = 0.015 / 1000
        
        input_cost = input_tokens * input_rate
        output_cost = output_tokens * output_rate
        
        return input_cost + output_cost
    
    # PR Comments Analysis Methods
    def generate_llmtxt_guidelines(self, all_comments: List[Dict], existing_content: str = "", quiet: bool = False) -> str:
        """
        Generate concise, consolidated coding guidelines from PR comments.
        
        Args:
            all_comments: List of PR comments with their classifications and context
            existing_content: Existing guidelines content to build upon if any
            quiet: Whether to suppress progress information
            
        Returns:
            str: Generated guidelines in LLM-friendly format
        """
        # Format comments as context
        comments_text = ""
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
            content_length = len(existing_content)
            if content_length > 20000:  # If content is very large
                if not quiet:
                    print(f"Large existing content detected ({content_length} chars). Optimizing...")
                # Extract the most important sections
                import re
                toc_match = re.search(r'## Table of Contents.*?(?=##\s+\w+|$)', existing_content, re.DOTALL)
                toc_section = toc_match.group(0) if toc_match else ""
                start_content = existing_content[:10000]
                end_content = existing_content[-5000:] if len(existing_content) > 5000 else ""
                optimized_content = f"{toc_section}\n\n{start_content}\n\n...\n[Content truncated for efficiency]\n\n{end_content}"
                prompt = UnifiedConfig.LLMTXT_UPDATE_PROMPT.format(existing_content=optimized_content, comments_text=comments_text)
            else:
                prompt = UnifiedConfig.LLMTXT_UPDATE_PROMPT.format(existing_content=existing_content, comments_text=comments_text)
            prompt_type = "Updating existing guidelines"
        else:
            prompt = UnifiedConfig.LLMTXT_GENERATION_PROMPT.format(comments_text=comments_text)
            prompt_type = "Generating new guidelines"
        
        try:
            if not quiet:
                print(f"\n{prompt_type} with LLM...")
            
            max_tokens = min(10000, UnifiedConfig.MAX_TOKENS_PER_CALL)
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}]
            })
            
            response = self.tracked_invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                return content[0].get('text', '').strip()
            
            logger.warning(f"Unexpected response structure: {response_body}")
            return "Unable to generate coding guidelines."
            
        except Exception as e:
            logger.error(f"Error generating coding guidelines: {e}")
            return f"Error generating coding guidelines: {str(e)}"
    
    def classify_comment(self, code_snippet: str, comment: str) -> str:
        """
        Classify a comment into one of three categories.
        
        Args:
            code_snippet: Code context for the comment
            comment: The comment text
            
        Returns:
            str: 'code_standards', 'discussions', or 'general'
        """
        prompt = UnifiedConfig.COMMENT_CLASSIFICATION_PROMPT.format(
            code_snippet=code_snippet,
            comment=comment
        )
        
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": prompt}]
            })
            
            response = self.tracked_invoke_model(modelId=self.model_id, body=body)
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
            
            return 'general'
            
        except Exception as e:
            logger.error(f"Error classifying comment: {e}")
            return 'general'
    
    def classify_comments(self, combined_text: str, num_comments: int, quiet: bool = False) -> List[str]:
        """
        Classify multiple comments in a single call.
        
        Args:
            combined_text: Combined text of all comments with their context
            num_comments: Number of comments to classify
            quiet: Whether to show progress
            
        Returns:
            list: List of classifications
        """
        structured_prompt = f"""
{UnifiedConfig.COMMENT_CLASSIFICATION_PROMPT}

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
            if not quiet:
                print(f"\nClassifying {num_comments} comments with LLM...")
            
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": structured_prompt}]
            })
            
            response = self.tracked_invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response.get('body').read())
            content = response_body.get('content', [{}])
            
            if content and content[0].get('type') == 'text':
                result = content[0].get('text', '').strip()
                classifications = []
                inferences = []
                
                responses = result.split('\n\n')
                for response in responses:
                    if not response.strip():
                        continue
                    
                    lines = response.strip().split('\n')
                    classification_line = lines[0].lower().strip()
                    
                    if 'code_standards' in classification_line:
                        classifications.append('code_standards')
                        if len(lines) > 1 and lines[1].strip():
                            inferences.append(lines[1].strip())
                        else:
                            inferences.append('')
                    elif 'discussions' in classification_line:
                        classifications.append('discussions')
                        inferences.append('')
                    else:
                        classifications.append('general')
                        inferences.append('')
                
                self.inferences = inferences
                
                # Ensure we return exactly num_comments classifications
                if len(classifications) < num_comments:
                    classifications.extend(['general'] * (num_comments - len(classifications)))
                elif len(classifications) > num_comments:
                    classifications = classifications[:num_comments]
                
                return classifications
            
            return ['general'] * num_comments
            
        except Exception as e:
            logger.error(f"Error classifying comments: {e}")
            return ['general'] * num_comments
    
    # Documentation Generation Methods
    def generate_documentation(self, prompt: str) -> str:
        """
        Generate documentation using AWS Bedrock.
        
        Args:
            prompt: The prompt to send to the LLM
            
        Returns:
            Generated documentation as string
        """
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.config['max_tokens'],
                "temperature": self.config['temperature'],
                "top_p": self.config['top_p'],
                "messages": [{"role": "user", "content": prompt}]
            })
            
            response = self.tracked_invoke_model(modelId=self.model_id, body=body)
            response_body = json.loads(response.get('body').read())
            
            if 'content' in response_body and response_body['content']:
                generated_text = response_body['content'][0]['text']
                
                # Print running cost after each successful request
                current_cost = self.total_cost
                print(f"      API call completed. Running cost: ${current_cost:.4f}")
                
                return generated_text.strip()
            
            raise RuntimeError("Unexpected response format from Bedrock")
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate documentation: {e}")
    
    def get_cost_report(self) -> Dict[str, Any]:
        """
        Get a report of token usage and costs.
        
        Returns:
            dict: Token usage and cost information
        """
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "total_cost": round(self.total_cost, 4),
            "total_requests": self.total_requests,
            "cost_breakdown": {
                "input_cost": round(self.calculate_cost(self.model_id, self.input_tokens, 0), 4),
                "output_cost": round(self.calculate_cost(self.model_id, 0, self.output_tokens), 4)
            }
        }
    
    def get_usage_stats(self) -> Dict[str, int]:
        """
        Get usage statistics for compatibility with documentation tool.
        
        Returns:
            Dictionary with usage statistics
        """
        return {
            'total_requests': self.total_requests,
            'total_tokens_used': self.output_tokens
        }
    
    def estimate_cost(self, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """
        Estimate cost for given token usage or return current total cost.
        
        Args:
            input_tokens: Number of input tokens (optional)
            output_tokens: Number of output tokens (optional)
            
        Returns:
            float: Estimated cost in USD
        """
        if input_tokens == 0 and output_tokens == 0:
            # Return current total cost if no tokens specified
            return self.total_cost
        else:
            # Calculate cost for specified tokens
            return self.calculate_cost(self.model_id, input_tokens, output_tokens)
    
    @property
    def total_tokens_used(self) -> int:
        """
        Get total tokens used (for compatibility with documentation assembly).
        
        Returns:
            int: Total output tokens used
        """
        return self.output_tokens
    
    def validate_connection(self) -> bool:
        """
        Validate connection to Bedrock service.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            bedrock_client = boto3.client(
                service_name='bedrock',
                region_name=self.region
            )
            bedrock_client.list_foundation_models()
            return True
        except Exception as e:
            print(f"Bedrock connection validation failed: {e}")
            return False
