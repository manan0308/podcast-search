"""
Settings router for API key management.

Provides endpoints for:
- Viewing API key status (masked)
- Updating API keys
- Validating API keys
"""
import os
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import httpx
from loguru import logger

from app.dependencies import AdminAuth
from app.config import settings

router = APIRouter()


class ApiKeyStatus(BaseModel):
    """Status of an API key."""
    name: str
    env_var: str
    configured: bool
    masked_value: Optional[str] = None
    valid: Optional[bool] = None
    error: Optional[str] = None


class ApiKeyUpdate(BaseModel):
    """Request to update an API key."""
    env_var: str
    value: str


class ApiKeyValidation(BaseModel):
    """Validation result for an API key."""
    valid: bool
    error: Optional[str] = None


# Supported API keys
API_KEYS = {
    "OPENAI_API_KEY": {
        "name": "OpenAI",
        "validate_url": "https://api.openai.com/v1/models",
        "header_name": "Authorization",
        "header_format": "Bearer {key}",
    },
    "ANTHROPIC_API_KEY": {
        "name": "Anthropic",
        "validate_url": "https://api.anthropic.com/v1/messages",
        "header_name": "x-api-key",
        "header_format": "{key}",
        # Anthropic needs a POST with minimal body
        "method": "POST",
        "body": {"model": "claude-3-haiku-20240307", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
    },
    "ASSEMBLYAI_API_KEY": {
        "name": "AssemblyAI",
        "validate_url": "https://api.assemblyai.com/v2/transcript",
        "header_name": "authorization",
        "header_format": "{key}",
    },
    "DEEPGRAM_API_KEY": {
        "name": "Deepgram",
        "validate_url": "https://api.deepgram.com/v1/projects",
        "header_name": "Authorization",
        "header_format": "Token {key}",
    },
}


def mask_key(key: str) -> str:
    """Mask an API key for display."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def get_env_file_path() -> Path:
    """Get path to .env file."""
    # Check multiple locations
    backend_dir = Path(__file__).parent.parent.parent
    locations = [
        backend_dir / ".env",
        backend_dir.parent / ".env",
    ]
    
    for path in locations:
        if path.exists():
            return path
    
    # Default to backend/.env (will be created)
    return backend_dir / ".env"


def read_env_file() -> dict:
    """Read current .env file contents."""
    env_path = get_env_file_path()
    env_vars = {}
    
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip()] = value
    
    return env_vars


def write_env_file(env_vars: dict):
    """Write .env file with updated values."""
    env_path = get_env_file_path()
    
    # Read existing file to preserve comments and order
    lines = []
    updated_keys = set()
    
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, _ = stripped.partition("=")
                    key = key.strip()
                    if key in env_vars:
                        lines.append(f"{key}={env_vars[key]}\n")
                        updated_keys.add(key)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
    
    # Add new keys that weren't in the file
    for key, value in env_vars.items():
        if key not in updated_keys:
            lines.append(f"{key}={value}\n")
    
    # Write back
    with open(env_path, "w") as f:
        f.writelines(lines)


@router.get("/api-keys")
async def get_api_key_status(_: AdminAuth) -> list[ApiKeyStatus]:
    """
    Get status of all API keys.
    
    Returns masked values and configuration status.
    Does NOT return actual key values for security.
    """
    result = []
    
    for env_var, config in API_KEYS.items():
        # Check if key is set (from environment or .env)
        key_value = os.environ.get(env_var) or getattr(settings, env_var, None)
        
        status = ApiKeyStatus(
            name=config["name"],
            env_var=env_var,
            configured=bool(key_value),
            masked_value=mask_key(key_value) if key_value else None,
        )
        result.append(status)
    
    return result


@router.post("/api-keys/validate")
async def validate_api_key(request: ApiKeyUpdate, _: AdminAuth) -> ApiKeyValidation:
    """
    Validate an API key by making a test request.
    
    Does NOT save the key, just tests if it works.
    """
    if request.env_var not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown API key: {request.env_var}"
        )
    
    config = API_KEYS[request.env_var]
    
    # Build headers
    headers = {
        config["header_name"]: config["header_format"].format(key=request.value),
        "Content-Type": "application/json",
    }
    
    # Add Anthropic-specific headers
    if request.env_var == "ANTHROPIC_API_KEY":
        headers["anthropic-version"] = "2023-06-01"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            method = config.get("method", "GET")
            
            if method == "POST":
                response = await client.post(
                    config["validate_url"],
                    headers=headers,
                    json=config.get("body", {}),
                )
            else:
                response = await client.get(config["validate_url"], headers=headers)
            
            # Most APIs return 401/403 for invalid keys
            if response.status_code in (401, 403):
                return ApiKeyValidation(valid=False, error="Invalid API key")
            
            # For Anthropic, 400 with "credit" message means valid but no credits
            if response.status_code == 400:
                body = response.text
                if "credit" in body.lower() or "billing" in body.lower():
                    return ApiKeyValidation(valid=True, error="Key valid but may need credits")
            
            # 200-299 means success
            if 200 <= response.status_code < 300:
                return ApiKeyValidation(valid=True)
            
            # Other errors
            return ApiKeyValidation(
                valid=False,
                error=f"Unexpected response: {response.status_code}"
            )
            
    except httpx.TimeoutException:
        return ApiKeyValidation(valid=False, error="Request timed out")
    except Exception as e:
        logger.error(f"API key validation error: {e}")
        return ApiKeyValidation(valid=False, error=str(e))


@router.post("/api-keys")
async def update_api_key(request: ApiKeyUpdate, _: AdminAuth):
    """
    Update an API key.
    
    Saves the key to .env file and updates the running environment.
    Requires admin authentication.
    """
    if request.env_var not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown API key: {request.env_var}"
        )
    
    # Read current env file
    env_vars = read_env_file()
    
    # Update the key
    env_vars[request.env_var] = request.value
    
    # Write back to file
    try:
        write_env_file(env_vars)
    except Exception as e:
        logger.error(f"Failed to write .env file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save API key: {str(e)}"
        )
    
    # Update running environment
    os.environ[request.env_var] = request.value
    
    logger.info(f"Updated API key: {request.env_var}")
    
    return {
        "status": "updated",
        "env_var": request.env_var,
        "masked_value": mask_key(request.value),
    }


@router.delete("/api-keys/{env_var}")
async def delete_api_key(env_var: str, _: AdminAuth):
    """
    Remove an API key.
    
    Removes from .env file and environment.
    """
    if env_var not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown API key: {env_var}"
        )
    
    # Read current env file
    env_vars = read_env_file()
    
    # Remove the key
    if env_var in env_vars:
        del env_vars[env_var]
        write_env_file(env_vars)
    
    # Remove from environment
    if env_var in os.environ:
        del os.environ[env_var]
    
    logger.info(f"Deleted API key: {env_var}")
    
    return {"status": "deleted", "env_var": env_var}

