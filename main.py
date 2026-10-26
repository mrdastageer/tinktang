from crewai import Crew, LLM
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from utils.config import Config
from utils.key_manager import validate_api_key, get_active_provider
from agents.planner import create_planner_agent
from agents.researcher import create_researcher_agent
from agents.executor import create_executor_agent
from agents.critic import create_critic_agent
from agents.orchestrator import create_orchestrator_agent
from agents.quick_response import create_quick_response_agent
from tasks.task_definitions import *

_FULL_PIPELINE_PATTERNS = (
    r"\b(?:research|compare|contrast|analy[sz]e|evaluate|assess|investigate|audit|plan|design|architect|break down)\b",
    r"\b(?:in[- ]depth|comprehensive|detailed|step[- ]by[- ]step|with (?:sources|citations|evidence)|pros and cons|trade[- ]offs)\b",
    r"\bfirst\b.*\bthen\b|\bafter that\b|\band then\b",
    r"\b(?:instagram|canva|campaign|poster|brochure|presentation|itinerary|proposal|business plan)\b",
)

_SIMPLE_QUERY_PATTERNS = (
    r"(?:hi|hello|hey|howdy|yo)(?: there)?",
    r"(?:hi|hello|hey)(?: there)? (?:how are you(?: doing| today)?|how's it going|what's up)",
    r"(?:how are you(?: doing| today)?|how's it going|what's up|how have you been)",
    r"(?:good morning|good afternoon|good evening)(?: there)?",
    r"(?:thanks|thank you|thx)(?: so much)?",
    r"(?:bye|goodbye|see you(?: later)?|good night)",
    r"(?:what is|what's|who is|who's|where is|when is|how many|how much)\b.+",
    r"what does .+ mean",
    r"(?:define|calculate|solve|translate|convert|spell)\b.+",
    r"(?:write|draft|create)\b.{0,80}\b(?:short|brief|one[- ]sentence|birthday message|greeting|caption)\b",
)


def requires_full_pipeline(query):
    normalized_query = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9'()+*/%.\-=\s]", " ", str(query).lower())).strip()
    if not normalized_query:
        return False
    if len(normalized_query.split()) >= 12:
        return True
    if any(re.search(pattern, normalized_query) for pattern in _FULL_PIPELINE_PATTERNS):
        return True
    if re.fullmatch(r"(?:(?:what is|calculate|solve)\s+)?[\d\s()+\-*/%.=]+\??", normalized_query):
        return False
    return not any(re.fullmatch(pattern, normalized_query) for pattern in _SIMPLE_QUERY_PATTERNS)

class PipelineResult:
    """Structured result object for pipeline outputs"""
    def __init__(self, query, plan=None, research=None, draft=None,
                 critique=None, final_score=None, revision_count=0,
                 final_output=None, elapsed_seconds=0.0, success=True):
        self.query = query
        self.plan = plan
        self.research = research
        self.draft = draft
        self.critique = critique
        self.final_score = final_score
        self.revision_count = revision_count
        self.final_output = final_output
        self.elapsed_seconds = elapsed_seconds
        self.success = success

class ThinkTank:
    AGENT_FACTORY_MAP = {
        "planner": create_planner_agent,
        "researcher": create_researcher_agent,
        "executor": create_executor_agent,
        "critic": create_critic_agent,
        "orchestrator": create_orchestrator_agent,
        "quick_response_agent": create_quick_response_agent,
    }
    _LLM_CACHE = {}

    def __init__(self, provider=None, model_name=None, api_key=None, agent_models=None):
        self._llm_cache = self.__class__._LLM_CACHE
        # Resolve provider and model from explicit inputs or .env first so the per-agent map
        # can default to the active provider when it is not explicitly overridden.
        self.provider, self.model = get_active_provider(provider=provider, api_key=api_key, model_name=model_name)
        self.agent_models = self._normalize_agent_models(agent_models, default_provider=self.provider)

        # Load API key (from parameter or .env)
        self.api_key = api_key or Config.get_api_key(self.provider)

        # Validate API key format for the resolved provider
        valid, msg = validate_api_key(self.provider, self.api_key)
        if not valid:
            raise ValueError(f"API key error for {self.provider}: {msg}")

        # Initialize default LLM and then agent-specific overrides.
        self.llm = self._init_llm_for_model(self.provider, self.model, self.api_key)
        self.planner = self._create_agent("planner")
        self.researcher = self._create_agent("researcher")
        self.executor = self._create_agent("executor")
        self.critic = self._create_agent("critic")
        self.orchestrator = self._create_agent("orchestrator")
        self.quick_response_agent = self._create_agent("quick_response_agent")

        if self.provider == "nvidia-nim":
            for agent in (
                self.planner,
                self.researcher,
                self.executor,
                self.critic,
                self.orchestrator,
                self.quick_response_agent,
            ):
                agent.use_system_prompt = False

    @staticmethod
    def _normalize_agent_key(agent_name):
        normalized = str(agent_name).strip().lower().replace("-", "_")
        aliases = {
            "quick_response": "quick_response_agent",
            "quickresponse": "quick_response_agent",
        }
        return aliases.get(normalized, normalized)

    def _normalize_agent_models(self, agent_models, default_provider=None):
        normalized = {}
        if not agent_models:
            return normalized
        fallback_provider = default_provider or getattr(self, "provider", None)
        for agent_name, config in agent_models.items():
            key = self._normalize_agent_key(agent_name)
            if key not in self.AGENT_FACTORY_MAP:
                raise ValueError(f"Unsupported agent '{agent_name}'")
            if isinstance(config, dict):
                provider = config.get("provider") or fallback_provider
                model_name = config.get("model_name") or config.get("model")
                if not model_name:
                    raise ValueError(f"Model name missing for agent '{agent_name}'")
                normalized[key] = {"provider": provider, "model_name": model_name}
            else:
                normalized[key] = {"provider": fallback_provider, "model_name": str(config)}
        return normalized

    def _resolve_agent_model(self, agent_name, provider=None, model_name=None):
        key = self._normalize_agent_key(agent_name)
        config = self.agent_models.get(key)
        if config:
            provider = provider or config.get("provider") or self.provider
            model_name = model_name or config.get("model_name") or config.get("model") or self.model
        return provider or self.provider, model_name or self.model

    def _create_agent(self, agent_name):
        factory = self.AGENT_FACTORY_MAP[agent_name]
        return factory(self._build_agent_llm(agent_name))

    def _build_agent_llm(self, agent_name, provider=None, model_name=None):
        provider, model_name = self._resolve_agent_model(agent_name, provider=provider, model_name=model_name)
        return self._init_llm_for_model(provider, model_name, self._get_provider_api_key_for(provider))

    def _get_provider_api_key_for(self, provider=None):
        provider = provider or self.provider
        if self.api_key and provider == self.provider:
            return self.api_key
        if provider == "google-gemini":
            return Config.GOOGLE_API_KEY
        if provider == "nvidia-nim":
            return Config.NVIDIA_API_KEY
        if provider == "omniroute":
            return Config.OMNIROUTE_API_KEY
        if provider == "meta-model-api":
            return Config.META_MODEL_API_KEY
        return None

    def _llm_cache_key(self, provider, model_name, api_key=None):
        self._llm_cache = getattr(self, "_llm_cache", self.__class__._LLM_CACHE)
        safe_model = model_name or self.model
        if provider == "google-gemini":
            safe_model = safe_model if safe_model.startswith("gemini/") else f"gemini/{safe_model}"
        elif provider in {"nvidia-nim", "omniroute", "meta-model-api"}:
            safe_model = f"openai/{safe_model}"

        base_url = {
            "google-gemini": None,
            "nvidia-nim": Config.NVIDIA_BASE_URL,
            "omniroute": Config.OMNIROUTE_BASE_URL,
            "meta-model-api": Config.META_MODEL_API_BASE_URL,
        }.get(provider)

        return (provider, safe_model, base_url, api_key or self._get_provider_api_key_for(provider))

    def _init_llm_for_model(self, provider, model_name, api_key=None):
        self._llm_cache = getattr(self, "_llm_cache", self.__class__._LLM_CACHE)
        api_key = api_key or self._get_provider_api_key_for(provider)
        safe_model = model_name or self.model
        cache_key = self._llm_cache_key(provider, safe_model, api_key)
        cached = self._llm_cache.get(cache_key)
        if cached is not None:
            return cached

        if provider == "google-gemini":
            model = safe_model if safe_model.startswith("gemini/") else f"gemini/{safe_model}"
            llm = LLM(
                model=model,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif provider == "nvidia-nim":
            llm = LLM(
                model=f"openai/{safe_model}",
                base_url=Config.NVIDIA_BASE_URL,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif provider == "omniroute":
            llm = LLM(
                model=f"openai/{safe_model}",
                base_url=Config.OMNIROUTE_BASE_URL,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif provider == "meta-model-api":
            llm = LLM(
                model=f"openai/{safe_model}",
                base_url=Config.META_MODEL_API_BASE_URL,
                temperature=Config.TEMPERATURE,
                max_tokens=max(Config.MAX_TOKENS, 8192),
                reasoning_effort="minimal",
                timeout=90,
                api_key=api_key
            )
        else:
            raise ValueError(
                f"Unsupported provider '{provider}'. "
                "ThinkTank supports 'google-gemini', 'nvidia-nim', 'omniroute', and 'meta-model-api'."
            )

        self._llm_cache[cache_key] = llm
        return llm

    def set_agent_model(self, agent_name, model_name, provider=None):
        key = self._normalize_agent_key(agent_name)
        if key not in self.AGENT_FACTORY_MAP:
            raise ValueError(f"Unsupported agent '{agent_name}'")

        resolved_provider, resolved_model = self._resolve_agent_model(key, provider=provider, model_name=model_name)
        self.agent_models[key] = {"provider": resolved_provider, "model_name": resolved_model}
        setattr(self, key, self._create_agent(key))

    def change_model(self, model_name, provider=None):
        """Replace the active provider/model and rebuild all agents."""
        model_name = model_name.strip()
        if not model_name:
            raise ValueError("Model name cannot be empty")

        provider = provider or self.provider
        if model_name not in self.list_available_models(provider):
            raise ValueError(
                f"Model '{model_name}' is not listed as a chat model for {provider}"
            )

        api_key = self.api_key if provider == self.provider else None
        replacement = ThinkTank(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            agent_models=dict(self.agent_models),
        )
        self.__dict__.update(replacement.__dict__)

    def list_available_models(self, provider):
        """Fetch usable model IDs from a configured provider endpoint."""
        api_key = self.api_key if provider == self.provider else Config.get_api_key(provider)
        if not api_key:
            raise ValueError(f"No API key configured for {provider}")

        if provider == "omniroute":
            return [Config.OMNIROUTE_MODEL]
        if provider == "meta-model-api":
            return [Config.META_MUSE_MODEL]

        if provider == "google-gemini":
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": api_key}
        elif provider == "nvidia-nim":
            url = f"{Config.NVIDIA_BASE_URL.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"model list request failed with HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"model list request failed: {error.reason}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("model list endpoint returned invalid JSON") from error

        if provider == "google-gemini":
            return [
                model["name"].removeprefix("models/")
                for model in payload.get("models", [])
                if "generateContent" in model.get("supportedGenerationMethods", [])
            ]

        non_chat_markers = {
            "embed", "embedding", "embeddings", "parse", "parser",
            "rerank", "reranker", "moderation", "classification",
        }
        model_ids = []
        for model in payload.get("data", []):
            model_id = model.get("id")
            if not model_id:
                continue

            id_tokens = set(re.split(r"[^a-z0-9]+", model_id.lower()))
            task = model.get("task", model.get("capability", ""))
            task_tokens = set(re.split(r"[^a-z0-9]+", str(task).lower()))
            if (id_tokens | task_tokens).isdisjoint(non_chat_markers):
                model_ids.append(model_id)

        return model_ids

    def process_query(self, user_query):
        """Main processing pipeline"""

        if not requires_full_pipeline(user_query):
            started_at = time.perf_counter()
            quick_task = create_quick_response_task(self.quick_response_agent, user_query)
            quick_crew = Crew(
                agents=[self.quick_response_agent],
                tasks=[quick_task],
                verbose=False,
                max_rpm=10,
            )
            quick_result = quick_crew.kickoff()
            quick_output = str(quick_result).strip() if quick_result is not None else ""
            return PipelineResult(
                query=user_query,
                final_output=quick_output,
                elapsed_seconds=time.perf_counter() - started_at,
                success=bool(quick_output),
            )

        # Phase 1: Planning
        planning_task = create_planning_task(self.planner, user_query)
        crew_plan = Crew(
            agents=[self.planner],
            tasks=[planning_task],
            verbose=True,
            max_rpm=10
        )
        plan_result = crew_plan.kickoff()

        # Phase 2: Research
        research_task = create_research_task(self.researcher, plan_result)
        crew_research = Crew(
            agents=[self.researcher],
            tasks=[research_task],
            verbose=True,
            max_rpm=10
        )
        research_result = crew_research.kickoff()

        # Phase 3: Execution with iterative critique
        max_attempts = Config.MAX_REVISION_ATTEMPTS
        attempt = 0
        approved_draft = None

        while attempt < max_attempts:
            # Execute
            execution_task = create_execution_task(
                self.executor,
                research_result
            )
            crew_execute = Crew(
                agents=[self.executor],
                tasks=[execution_task],
                verbose=True,
                max_rpm=10
            )
            draft = crew_execute.kickoff()

            # Critique
            critique_task = create_critique_task(self.critic, draft)
            crew_critique = Crew(
                agents=[self.critic],
                tasks=[critique_task],
                verbose=True,
                max_rpm=10
            )
            critique = crew_critique.kickoff()

            # Extract score
            score = self._extract_score(critique)

            if score >= Config.CRITIC_PASS_THRESHOLD:
                approved_draft = draft
                break

            attempt += 1
            print(f"Revision attempt {attempt}/{max_attempts}")

        if not approved_draft:
            approved_draft = draft  # Use last attempt

        # Phase 4: Orchestration
        orchestration_task = create_orchestration_task(
            self.orchestrator,
            approved_draft
        )
        crew_final = Crew(
            agents=[self.orchestrator],
            tasks=[orchestration_task],
            verbose=True,
            max_rpm=10
        )
        final_result = crew_final.kickoff()

        # Create PipelineResult with all pipeline data
        pipeline_result = PipelineResult(
            query=user_query,
            plan=plan_result,
            research=research_result,
            draft=approved_draft,
            critique=critique,
            final_score=score,
            revision_count=attempt,
            final_output=final_result,
            elapsed_seconds=0.0,  # Would need timing implementation
            success=True
        )

        return pipeline_result

    def _init_llm(self):
        """Initialize LLM based on selected provider"""
        api_key = self._get_provider_api_key()

        if self.provider == "google-gemini":
            # Ensure proper liteLLM format: 'gemini/model-name'
            model = self.model if self.model.startswith("gemini/") else f"gemini/{self.model}"
            return LLM(
                model=model,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif self.provider == "nvidia-nim":
            # NVIDIA NIM OpenAI-compatible endpoint
            base_url = Config.NVIDIA_BASE_URL
            return LLM(
                model=f"openai/{self.model}",
                base_url=base_url,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif self.provider == "omniroute":
            return LLM(
                model=f"openai/{self.model}",
                base_url=Config.OMNIROUTE_BASE_URL,
                temperature=Config.TEMPERATURE,
                max_tokens=Config.MAX_TOKENS,
                timeout=90,
                api_key=api_key
            )
        elif self.provider == "meta-model-api":
            return LLM(
                model=f"openai/{self.model}",
                base_url=Config.META_MODEL_API_BASE_URL,
                temperature=Config.TEMPERATURE,
                max_tokens=max(Config.MAX_TOKENS, 8192),
                reasoning_effort="minimal",
                timeout=90,
                api_key=api_key
            )
        else:
            raise ValueError(
                f"Unsupported provider '{self.provider}'. "
                "ThinkTank supports 'google-gemini', 'nvidia-nim', 'omniroute', and 'meta-model-api'."
            )

    def _get_provider_api_key(self):
        """Get API key — prefer the key passed at construction time"""
        if self.api_key:
            return self.api_key
        if self.provider == "google-gemini":
            return Config.GOOGLE_API_KEY
        elif self.provider == "nvidia-nim":
            return Config.NVIDIA_API_KEY
        elif self.provider == "omniroute":
            return Config.OMNIROUTE_API_KEY
        elif self.provider == "meta-model-api":
            return Config.META_MODEL_API_KEY
        return None

    def _extract_score(self, critique_text):
        """Extract quality score from critique"""
        import re
        critique_text = str(critique_text)

        for pattern in [
            r'(?:overall\s+score|quality\s+rating|score)[^\d]*(\d+(?:\.\d+)?)\s*(?:/\s*10|out\s+of\s+10|of\s+10)?',
            r'(\d+(?:\.\d+)?)\s*/\s*10',
        ]:
            match = re.search(pattern, critique_text, re.I)
            if match:
                return float(match.group(1))

        return 5.0  # Default middle score

# CLI Interface
def main():
    print("=" * 60)
    print("ThinkTank - Multi-Agent System")
    print("=" * 60)

    thinktank = ThinkTank()
    providers = {"google-gemini", "nvidia-nim", "omniroute", "meta-model-api"}
    model_catalogs = {}

    while True:
        print("\nEnter your query, '/models' to change the model, or 'exit' to quit:")
        query = input("> ").strip()

        if query.lower() in ['exit', 'quit']:
            print("Thank you for using ThinkTank!")
            break

        if query.lower() == "/models" or query.lower().startswith("/models "):
            arguments = query.split(maxsplit=2)
            provider = thinktank.provider
            model_name = ""

            if len(arguments) == 1:
                providers_to_list = sorted(providers)
            elif len(arguments) == 2 and arguments[1] in providers:
                providers_to_list = [arguments[1]]
            elif len(arguments) == 3 and arguments[1] in providers:
                provider, model_name = arguments[1], arguments[2]
            else:
                model_name = query[len("/models"):].strip()

            if len(arguments) == 1 or (len(arguments) == 2 and arguments[1] in providers):
                print(f"Current model: {thinktank.provider} / {thinktank.model}")
                for listed_provider in providers_to_list:
                    print(f"\n{listed_provider} models:")
                    try:
                        model_ids = thinktank.list_available_models(listed_provider)
                        model_catalogs[listed_provider] = set(model_ids)
                        if model_ids:
                            for model_id in model_ids:
                                print(f"  {model_id}")
                        else:
                            print("  No usable models returned.")
                    except (RuntimeError, ValueError) as error:
                        print(f"  Could not list models: {error}")
                print("\nSwitch with: /models <provider> <model-id>")
                continue

            if not model_name:
                continue

            matching_providers = [
                listed_provider
                for listed_provider, model_ids in model_catalogs.items()
                if model_name in model_ids
            ]
            if len(arguments) == 2 and arguments[1] not in providers:
                if len(matching_providers) == 1:
                    provider = matching_providers[0]
                elif len(matching_providers) > 1:
                    print(f"Model ID is listed by multiple providers. Specify one: {', '.join(matching_providers)}")
                    continue
                else:
                    print("Unknown model ID. Run '/models' to list provider models, or use '/models <provider> <model-id>'.")
                    continue

            try:
                thinktank.change_model(model_name, provider=provider)
                print(f"Active model changed to {thinktank.provider} / {thinktank.model}")
            except ValueError as error:
                print(f"Could not change model: {error}")
            continue

        if not query:
            continue

        print("\nThinkTank is processing your query...\n")
        result = thinktank.process_query(query)
        print("\n" + "=" * 60)
        print("FINAL RESULT:")
        print("=" * 60)
        print(result)
        print("=" * 60)

if __name__ == "__main__":
    main()
