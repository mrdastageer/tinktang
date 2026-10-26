"""
Secure API Key Manager for ThinkTank Multi-Agent System

Provides validation and retrieval of API keys loaded exclusively from .env.
"""

import os
import re
import logging
from typing import Optional, Tuple
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Map provider ID to its corresponding .env variable name
PROVIDER_ENV_MAP = {
    "google-gemini": "GOOGLE_API_KEY",
    "nvidia-nim": "NVIDIA_API_KEY",
    "omniroute": "OMNIROUTE_API_KEY",
    "meta-model-api": "MODEL_API_KEY",
}


class SecureKeyManager:
    """Manages secure validation and retrieval of API keys from .env."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        self.config_path = config_path
        load_dotenv(self.config_path, override=True)

    def _reload_env(self):
        """Reload .env to pick up any changes on disk."""
        load_dotenv(self.config_path, override=True)

    def _validate_key_format(self, provider: str, key: str) -> Tuple[bool, str]:
        """Validate API key format for specific provider."""
        if not key or len(key.strip()) == 0:
            return False, "API key is empty"

        key = key.strip()

        if provider == "google-gemini":
            if not key.startswith("AIza"):
                return False, "Google Gemini key must start with 'AIza'"
            if len(key) < 35:
                return False, "Google Gemini key is too short"

        elif provider == "nvidia-nim":
            if not key.startswith("nvapi-"):
                return False, "NVIDIA NIM key must start with 'nvapi-'"
            if len(key) < 35:
                return False, "NVIDIA NIM key is too short"

        elif provider == "omniroute":
            if len(key) < 1:
                return False, "OmniRoute API key is empty"

        elif provider == "meta-model-api":
            if len(key) < 1:
                return False, "Meta Model API key is empty"

        else:
            return False, f"Unknown provider: {provider}"

        return True, "Key format valid"

    def get_api_key(self, provider: str) -> Optional[str]:
        """Retrieve API key for specified provider from .env."""
        self._reload_env()
        env_var = PROVIDER_ENV_MAP.get(provider)
        if env_var:
            return os.getenv(env_var)
        return None

    def validate_api_key(self, provider: str, key: str = None) -> Tuple[bool, str]:
        """Validate API key from argument or from .env."""
        try:
            if key is None:
                key = self.get_api_key(provider)
                if not key:
                    env_var = PROVIDER_ENV_MAP.get(provider, "API_KEY")
                    return False, f"Missing {env_var} in .env file"

            format_valid, format_msg = self._validate_key_format(provider, key)
            if not format_valid:
                return False, format_msg

            if len(key) < 32:
                return False, "API key is too short (minimum 32 characters)"

            return True, "API key is valid"

        except Exception as e:
            logger.error(f"API key validation failed for {provider}: {str(e)}")
            return False, f"Validation error: {str(e)}"

    def get_key_status(self) -> dict:
        """Get comprehensive status of all configured API keys"""
        status = {}
        self._reload_env()

        for provider, env_var in PROVIDER_ENV_MAP.items():
            key = os.getenv(env_var)
            status[provider] = {
                "configured": bool(key),
                "valid_format": False,
                "length": len(key) if key else 0,
                "message": "Not configured"
            }

            if key:
                format_valid, format_msg = self._validate_key_format(provider, key)
                status[provider]["valid_format"] = format_valid
                status[provider]["message"] = format_msg

        return status

    def get_active_provider(self, provider: str = None, api_key: str = None, model_name: str = None) -> Tuple[str, str]:
        """Determine active provider based on explicit choice or configured .env keys."""
        self._reload_env()

        # 1. Explicit provider requested
        if provider and provider in PROVIDER_ENV_MAP:
            env_var = PROVIDER_ENV_MAP[provider]
            key = api_key or os.getenv(env_var)
            if not key:
                raise ValueError(f"Missing {env_var} in .env for provider '{provider}'. Please set it in your .env file.")
            valid, msg = self._validate_key_format(provider, key)
            if not valid:
                raise ValueError(f"Invalid {env_var} format in .env: {msg}")
            if not model_name:
                model_name = self._get_default_model(provider)
            return provider, model_name

        # 2. Check if a key string was directly supplied
        if api_key:
            for prov in PROVIDER_ENV_MAP:
                prefix = "AIza" if prov == "google-gemini" else "nvapi-"
                if prov == "omniroute" or api_key.strip().startswith(prefix):
                    if not model_name:
                        model_name = self._get_default_model(prov)
                    return prov, model_name

        # 3. Check configured .env variables in priority order
        for prov, env_var in PROVIDER_ENV_MAP.items():
            env_key = os.getenv(env_var)
            if env_key and self._validate_key_format(prov, env_key)[0]:
                if not model_name:
                    model_name = self._get_default_model(prov)
                return prov, model_name

        raise ValueError(
            "No valid API key found. Configure GOOGLE_API_KEY, NVIDIA_API_KEY, or OMNIROUTE_API_KEY."
        )

    def _get_default_model(self, provider: str) -> str:
        """Get default model for provider."""
        if provider == "google-gemini":
            return os.getenv("MODEL_NAME", "gemini-3-flash-preview")
        elif provider == "nvidia-nim":
            return os.getenv("NVIDIA_MODEL_NAME", "nvidia/nemotron-3.5-lightning-30b-a3b")
        elif provider == "omniroute":
            return os.getenv("OMNIROUTE_MODEL", os.getenv("ANTHROPIC_MODEL", "ThinkTank"))
        elif provider == "meta-model-api":
            return os.getenv("META_MUSE_MODEL", "muse-spark-1.1")
        else:
            raise ValueError(f"No default model for unsupported provider '{provider}'")


# Global key manager singleton
_key_manager_instance = None

def get_key_manager() -> SecureKeyManager:
    global _key_manager_instance
    if _key_manager_instance is None:
        _key_manager_instance = SecureKeyManager()
    return _key_manager_instance

def validate_api_key(provider: str, key: str = None) -> Tuple[bool, str]:
    return get_key_manager().validate_api_key(provider, key)

def get_active_provider(provider: str = None, api_key: str = None, model_name: str = None) -> Tuple[str, str]:
    return get_key_manager().get_active_provider(provider=provider, api_key=api_key, model_name=model_name)
