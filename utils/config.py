import os
from dotenv import load_dotenv
from utils.key_manager import get_key_manager

load_dotenv()

_DEFAULT_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not _DEFAULT_SERVICE_ACCOUNT_PATH:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    candidate = os.path.join(repo_root, "serviceAccountKey.json")
    if os.path.exists(candidate):
        _DEFAULT_SERVICE_ACCOUNT_PATH = candidate

class Config:
    # Key manager for secure API key handling
    key_manager = get_key_manager()

    # Environment-based configuration (for backward compatibility)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-pro")
    NVIDIA_MODEL_NAME = os.getenv("NVIDIA_MODEL_NAME", "nvidia/nemotron-3.5-lightning-30b-a3b")
    _omniroute_base_url = os.getenv("OMNIROUTE_BASE_URL", os.getenv("ANTHROPIC_BASE_URL", "http://localhost:20128")).rstrip("/")
    OMNIROUTE_BASE_URL = _omniroute_base_url if _omniroute_base_url.endswith("/v1") else _omniroute_base_url + "/v1"
    OMNIROUTE_API_KEY = os.getenv("OMNIROUTE_API_KEY", os.getenv("ANTHROPIC_AUTH_TOKEN"))
    OMNIROUTE_MODEL = os.getenv("OMNIROUTE_MODEL", os.getenv("ANTHROPIC_MODEL", "ThinkTank"))
    META_MODEL_API_KEY = os.getenv("MODEL_API_KEY", os.getenv("META_MODEL_API_KEY"))
    META_MODEL_API_BASE_URL = os.getenv("META_MODEL_API_BASE_URL", "https://api.meta.ai/v1").rstrip("/")
    META_MUSE_MODEL = os.getenv("META_MUSE_MODEL", "muse-spark-1.1")
    FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")
    FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN")
    FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID")
    FIRESTORE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
    serviceAccountKey = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", _DEFAULT_SERVICE_ACCOUNT_PATH)
    GOOGLE_APPLICATION_CREDENTIALS = serviceAccountKey
    TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", 2048))

    # Quality thresholds
    CRITIC_PASS_THRESHOLD = 6.0  # Score out of 10
    MAX_REVISION_ATTEMPTS = 2

    @classmethod
    def get_api_key(cls, provider: str) -> str:
        """Get API key for specified provider using key manager"""
        key = cls.key_manager.get_api_key(provider)
        if key:
            return key

        # Fallback to environment variables
        if provider == "google-gemini":
            return cls.GOOGLE_API_KEY
        elif provider == "nvidia-nim":
            return cls.NVIDIA_API_KEY
        elif provider == "omniroute":
            return cls.OMNIROUTE_API_KEY
        elif provider == "meta-model-api":
            return cls.META_MODEL_API_KEY
        else:
            return None

    @classmethod
    def set_api_key(cls, provider: str, key: str) -> bool:
        """Set API key for specified provider"""
        success, message = cls.key_manager.add_api_key(provider, key)
        if success:
            # Update environment variable
            env_var = "MODEL_API_KEY" if provider == "meta-model-api" else f"{provider.upper()}_API_KEY"
            os.environ[env_var] = key
            # Update class variable
            if provider == "google-gemini":
                cls.GOOGLE_API_KEY = key
            elif provider == "nvidia-nim":
                cls.NVIDIA_API_KEY = key
            elif provider == "meta-model-api":
                cls.META_MODEL_API_KEY = key
        return success

    @classmethod
    def validate_key(cls, provider: str, key: str = None) -> bool:
        """Validate API key for specified provider"""
        return cls.key_manager.validate_api_key(provider, key)[0]

    @classmethod
    def get_active_provider(cls, api_key: str = None, model_name: str = None) -> tuple:
        """Get active provider based on API key and model"""
        return cls.key_manager.get_active_provider(api_key, model_name)

    @classmethod
    def list_providers(cls) -> dict:
        """List all configured providers"""
        return cls.key_manager.list_stored_keys()

    @classmethod
    def get_key_status(cls) -> dict:
        """Get comprehensive status of all API keys"""
        return cls.key_manager.get_key_status()

    @classmethod
    def remove_api_key(cls, provider: str) -> bool:
        """Remove API key for specified provider"""
        success, message = cls.key_manager.remove_api_key(provider)
        if success:
            # Remove from environment variables
            env_var = "MODEL_API_KEY" if provider == "meta-model-api" else f"{provider.upper()}_API_KEY"
            if env_var in os.environ:
                del os.environ[env_var]
            # Update class variable
            if provider == "google-gemini":
                cls.GOOGLE_API_KEY = None
            elif provider == "nvidia-nim":
                cls.NVIDIA_API_KEY = None
            elif provider == "meta-model-api":
                cls.META_MODEL_API_KEY = None
        return success

    @classmethod
    def rotate_key(cls, provider: str, new_key: str) -> bool:
        """Rotate API key for specified provider"""
        success, message = cls.key_manager.rotate_key(provider, new_key)
        if success:
            # Update environment variable and class variable
            env_var = "MODEL_API_KEY" if provider == "meta-model-api" else f"{provider.upper()}_API_KEY"
            os.environ[env_var] = new_key
            if provider == "google-gemini":
                cls.GOOGLE_API_KEY = new_key
            elif provider == "nvidia-nim":
                cls.NVIDIA_API_KEY = new_key
            elif provider == "meta-model-api":
                cls.META_MODEL_API_KEY = new_key
        return success

    @classmethod
    def validate(cls) -> list:
        """Validate configuration and return list of problems (empty if all good)"""
        problems = []

        # Check required environment variables
        if not cls.GOOGLE_API_KEY and not cls.NVIDIA_API_KEY and not cls.OMNIROUTE_API_KEY and not cls.META_MODEL_API_KEY:
            problems.append("No API key configured. Set GOOGLE_API_KEY, NVIDIA_API_KEY, OMNIROUTE_API_KEY, or MODEL_API_KEY in .env")

        # Check temperature range
        if cls.TEMPERATURE < 0.0 or cls.TEMPERATURE > 1.0:
            problems.append(f"Temperature {cls.TEMPERATURE} is outside valid range [0.0, 1.0]")

        # Check max tokens
        if cls.MAX_TOKENS <= 0:
            problems.append(f"MAX_TOKENS {cls.MAX_TOKENS} must be positive")

        # Check critic threshold
        if cls.CRITIC_PASS_THRESHOLD < 0.0 or cls.CRITIC_PASS_THRESHOLD > 10.0:
            problems.append(f"CRITIC_PASS_THRESHOLD {cls.CRITIC_PASS_THRESHOLD} is outside valid range [0.0, 10.0]")

        # Check revision attempts
        if cls.MAX_REVISION_ATTEMPTS <= 0:
            problems.append(f"MAX_REVISION_ATTEMPTS {cls.MAX_REVISION_ATTEMPTS} must be positive")

        return problems
