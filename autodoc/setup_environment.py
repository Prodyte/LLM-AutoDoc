"""
Environment setup module for the unified CLI tool.
Handles setup of Node.js dependencies and AWS Bedrock validation.
"""
import subprocess
import os
from pathlib import Path
from typing import List, Tuple

from .unified_config import UnifiedConfig


def check_node_npm() -> Tuple[bool, str]:
    """Check if Node.js and npm are available."""
    try:
        # Check Node.js
        node_result = subprocess.run(["node", "--version"], 
                                   capture_output=True, text=True)
        if node_result.returncode != 0:
            return False, "Node.js not found"
        
        node_version = node_result.stdout.strip()
        
        # Check npm
        npm_result = subprocess.run(["npm", "--version"], 
                                  capture_output=True, text=True)
        if npm_result.returncode != 0:
            return False, "npm not found"
        
        npm_version = npm_result.stdout.strip()
        
        return True, f"Node.js {node_version}, npm {npm_version}"
        
    except FileNotFoundError:
        return False, "Node.js/npm not installed"
    except Exception as e:
        return False, f"Error checking Node.js/npm: {e}"


def setup_node_dependencies() -> bool:
    """Setup Node.js dependencies for JavaScript/TypeScript parsing."""
    print("Setting up Node.js dependencies...")
    
    # Check if Node.js and npm are available
    node_available, node_info = check_node_npm()
    if not node_available:
        print(f"✗ {node_info}")
        print("\nTo install Node.js:")
        print("  macOS: brew install node")
        print("  Ubuntu: sudo apt-get install nodejs npm")
        print("  Windows: Download from https://nodejs.org/")
        print("  Manual: https://nodejs.org/en/download/")
        return False
    
    print(f"✓ {node_info}")
    
    # Setup parsers directory
    current_dir = Path(__file__).parent
    parsers_dir = current_dir / "parsers"
    package_json = parsers_dir / "package.json"
    node_modules = parsers_dir / "node_modules"
    
    if not parsers_dir.exists():
        print(f"✗ Parsers directory not found: {parsers_dir}")
        return False
    
    if not package_json.exists():
        print(f"✗ package.json not found: {package_json}")
        return False
    
    if node_modules.exists():
        print("✓ Node.js dependencies already installed")
        return True
    
    print("Installing Node.js dependencies...")
    try:
        result = subprocess.run(
            ["npm", "install"],
            cwd=parsers_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ Node.js dependencies installed successfully")
            return True
        else:
            print(f"✗ Failed to install Node.js dependencies: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ Error installing Node.js dependencies: {e}")
        return False


def check_aws_credentials() -> Tuple[bool, str]:
    """Check if AWS credentials are configured."""
    try:
        # Check AWS CLI
        result = subprocess.run(["aws", "sts", "get-caller-identity"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            import json
            identity = json.loads(result.stdout)
            account = identity.get('Account', 'Unknown')
            arn = identity.get('Arn', 'Unknown')
            return True, f"Account: {account}, ARN: {arn}"
        else:
            return False, "AWS credentials not configured or invalid"
            
    except FileNotFoundError:
        return False, "AWS CLI not installed"
    except json.JSONDecodeError:
        return False, "Invalid AWS CLI response"
    except Exception as e:
        return False, f"Error checking AWS credentials: {e}"


def check_bedrock_access() -> Tuple[bool, str]:
    """Check if AWS Bedrock is accessible."""
    try:
        result = subprocess.run([
            "aws", "bedrock", "list-foundation-models", 
            "--region", UnifiedConfig.AWS_REGION
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return True, f"Bedrock accessible in {UnifiedConfig.AWS_REGION}"
        else:
            return False, f"Bedrock not accessible: {result.stderr}"
            
    except Exception as e:
        return False, f"Error checking Bedrock access: {e}"


def validate_bedrock_model() -> Tuple[bool, str]:
    """Validate that the configured Bedrock model is available."""
    try:
        from .unified_bedrock_client import UnifiedBedrockClient
        client = UnifiedBedrockClient()
        
        if client.validate_connection():
            return True, f"Model {UnifiedConfig.BEDROCK_MODEL_ID} is accessible"
        else:
            return False, f"Model {UnifiedConfig.BEDROCK_MODEL_ID} is not accessible"
            
    except Exception as e:
        return False, f"Error validating Bedrock model: {e}"


def setup_complete_environment() -> bool:
    """Setup the complete environment for the unified CLI tool."""
    print("🚀 ETC Context - Environment Setup")
    print("=" * 50)
    
    success = True
    
    # 1. Check and setup Node.js dependencies
    print("\n1. Node.js Dependencies")
    print("-" * 25)
    if not setup_node_dependencies():
        print("⚠️  JavaScript/TypeScript parsing will not work")
        success = False
    
    # 3. Check AWS credentials
    print("\n3. AWS Configuration")
    print("-" * 20)
    aws_available, aws_info = check_aws_credentials()
    if aws_available:
        print(f"✓ AWS credentials configured: {aws_info}")
    else:
        print(f"✗ {aws_info}")
        print("\nTo configure AWS:")
        print("  aws configure")
        print("  or set environment variables:")
        print("    export AWS_ACCESS_KEY_ID=your_key")
        print("    export AWS_SECRET_ACCESS_KEY=your_secret")
        success = False
    
    # 4. Check Bedrock access
    print("\n4. AWS Bedrock Access")
    print("-" * 22)
    if aws_available:
        bedrock_available, bedrock_info = check_bedrock_access()
        if bedrock_available:
            print(f"✓ {bedrock_info}")
            
            # 5. Validate specific model
            print("\n5. Bedrock Model Validation")
            print("-" * 30)
            model_available, model_info = validate_bedrock_model()
            if model_available:
                print(f"✓ {model_info}")
            else:
                print(f"✗ {model_info}")
                print(f"\nCurrent model: {UnifiedConfig.BEDROCK_MODEL_ID}")
                print("Make sure you have access to Claude models in AWS Bedrock console")
                success = False
        else:
            print(f"✗ {bedrock_info}")
            print(f"\nMake sure Bedrock is available in region: {UnifiedConfig.AWS_REGION}")
            success = False
    else:
        print("⚠️  Skipping Bedrock checks (AWS not configured)")
    
    # 6. Environment summary
    print("\n" + "=" * 50)
    if success:
        print("🎉 Environment setup completed successfully!")
        print("\nYou can now use all features:")
        print("  • PR comments mining")
        print("  • Documentation generation")
        print("  • JavaScript/TypeScript parsing")
        print("  • AWS Bedrock LLM integration")
    else:
        print("⚠️  Environment setup completed with warnings")
        print("\nSome features may not work properly.")
        print("Please address the issues above.")
    
    print("\n" + "=" * 50)
    return success


def run_diagnostics() -> None:
    """Run comprehensive diagnostics of the environment."""
    print("🔍 ETC Context - Environment Diagnostics")
    print("=" * 50)
    
    diagnostics = []
    
    # Check Node.js
    node_available, node_info = check_node_npm()
    diagnostics.append(("Node.js/npm", node_available, node_info))
    
    # Check Node modules
    current_dir = Path(__file__).parent
    node_modules = current_dir / "parsers" / "node_modules"
    node_deps_available = node_modules.exists()
    diagnostics.append(("Node.js dependencies", node_deps_available, 
                       "Installed" if node_deps_available else "Not installed"))
    
    # Check AWS
    aws_available, aws_info = check_aws_credentials()
    diagnostics.append(("AWS credentials", aws_available, aws_info))
    
    # Check Bedrock
    if aws_available:
        bedrock_available, bedrock_info = check_bedrock_access()
        diagnostics.append(("AWS Bedrock", bedrock_available, bedrock_info))
        
        if bedrock_available:
            model_available, model_info = validate_bedrock_model()
            diagnostics.append(("Bedrock model", model_available, model_info))
    
    # Print results
    print("\nDiagnostic Results:")
    print("-" * 20)
    for name, available, info in diagnostics:
        status = "✓" if available else "✗"
        print(f"{status} {name:<20} {info}")
    
    # Configuration summary
    print(f"\nCurrent Configuration:")
    print(f"  AWS Region: {UnifiedConfig.AWS_REGION}")
    print(f"  AWS Profile: {UnifiedConfig.AWS_PROFILE}")
    print(f"  Bedrock Model: {UnifiedConfig.BEDROCK_MODEL_ID}")
    print(f"  Supported Extensions: {', '.join(UnifiedConfig.SUPPORTED_EXTENSIONS)}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    setup_complete_environment()
