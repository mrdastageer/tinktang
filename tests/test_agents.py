"""
Unit Tests for ThinkTank Agents

Tests agent initialization, role definitions, and basic functionality.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestAgentCreation(unittest.TestCase):
    """Test suite for agent factory functions."""

    def setUp(self):
        """Set up mock LLM for testing."""
        # Create a simple mock LLM that will work with CrewAI Agent
        # CrewAI Agent expects llm to be either a string or a BaseLLM instance
        # We'll use a simple string for testing
        self.mock_llm = "test-model"

    def test_planner_agent_creation(self):
        """Test planner agent can be instantiated with correct role."""
        from agents.planner import create_planner_agent

        agent = create_planner_agent(self.mock_llm)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.role, "Strategic Planner")
        self.assertIn("strategist", agent.backstory.lower())

    def test_researcher_agent_creation(self):
        """Test researcher agent can be instantiated with correct role."""
        from agents.researcher import create_researcher_agent

        agent = create_researcher_agent(self.mock_llm)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.role, "Research Specialist")
        self.assertIn("research", agent.backstory.lower())

    def test_executor_agent_creation(self):
        """Test executor agent can be instantiated with correct role."""
        from agents.executor import create_executor_agent

        agent = create_executor_agent(self.mock_llm)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.role, "Content Executor")
        self.assertIn("writer", agent.backstory.lower())

    def test_critic_agent_creation(self):
        """Test critic agent can be instantiated with correct role."""
        from agents.critic import create_critic_agent

        agent = create_critic_agent(self.mock_llm)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.role, "Quality Critic")
        self.assertIn("quality", agent.backstory.lower())

    def test_orchestrator_agent_creation(self):
        """Test orchestrator agent can be instantiated with correct role."""
        from agents.orchestrator import create_orchestrator_agent

        agent = create_orchestrator_agent(self.mock_llm)
        self.assertIsNotNone(agent)
        self.assertEqual(agent.role, "Orchestrator")
        self.assertIn("synthesize", agent.backstory.lower())

    def test_quick_response_agent_creation(self):
        """Test the lightweight social-response agent can be instantiated."""
        from agents.quick_response import create_quick_response_agent

        agent = create_quick_response_agent(self.mock_llm)
        self.assertEqual(agent.role, "Direct Response Assistant")
        self.assertFalse(agent.allow_delegation)
        self.assertEqual(agent.max_iter, 1)

    def test_all_agents_unique_roles(self):
        """Verify all agents have unique role identifiers."""
        from agents.planner import create_planner_agent
        from agents.researcher import create_researcher_agent
        from agents.executor import create_executor_agent
        from agents.critic import create_critic_agent
        from agents.orchestrator import create_orchestrator_agent

        agents = [
            create_planner_agent(self.mock_llm),
            create_researcher_agent(self.mock_llm),
            create_executor_agent(self.mock_llm),
            create_critic_agent(self.mock_llm),
            create_orchestrator_agent(self.mock_llm),
        ]

        roles = [agent.role for agent in agents]
        self.assertEqual(len(roles), len(set(roles)), "All agent roles should be unique")


class TestScoreExtraction(unittest.TestCase):
    """Test suite for critic score parsing logic."""

    def test_extract_standard_score(self):
        """Test standard 'Overall Score: X' format."""
        from main import ThinkTank

        tt = ThinkTank()
        critique = "This is good work.\n\nOverall Score: 8.5\n\nStrengths: Clear and concise."
        score = tt._extract_score(critique)
        self.assertEqual(score, 8.5)

    def test_extract_fraction_score(self):
        """Test 'X/10' fraction format."""
        from main import ThinkTank

        tt = ThinkTank()
        critique = "Quality rating: 7.8/10"
        score = tt._extract_score(critique)
        self.assertEqual(score, 7.8)

    def test_extract_with_noise(self):
        """Test extraction from noisy text."""
        from main import ThinkTank

        tt = ThinkTank()
        critique = "Here's my evaluation...\nScore: 9.2 out of 10\nThis draft is excellent."
        score = tt._extract_score(critique)
        self.assertEqual(score, 9.2)

    def test_extract_default_fallback(self):
        """Test fallback to default when no score found."""
        from main import ThinkTank

        tt = ThinkTank()
        critique = "This is a critique with no numbers."
        score = tt._extract_score(critique)
        self.assertEqual(score, 5.0)  # Default fallback score


class TestSmallTalkRouting(unittest.TestCase):
    """Test task triage and the one-agent fast path."""

    def test_routes_simple_tasks_directly_and_complex_tasks_to_full_pipeline(self):
        from main import requires_full_pipeline

        for query in (
            "hi",
            "Hello!",
            "How are you?",
            "What is 2 + 2?",
            "Define photosynthesis in one sentence",
            "Write a short birthday message",
        ):
            with self.subTest(query=query):
                self.assertFalse(requires_full_pipeline(query))

        for query in (
            "Compare these two laptops and evaluate which is better for students",
            "Research renewable energy and provide sources",
            "Plan a three-day trip with a detailed daily itinerary",
            "Generate an Instagram Canva for SSSE college Tumakuru department fest",
            "1. Research the issue\n2. Compare alternatives\n3. Recommend a solution",
            "Explain the options, then calculate the cost and write a recommendation",
        ):
            with self.subTest(query=query):
                self.assertTrue(requires_full_pipeline(query))

    def test_simple_query_runs_only_quick_response_agent(self):
        from agents.quick_response import create_quick_response_agent
        from main import ThinkTank

        thinktank = ThinkTank.__new__(ThinkTank)
        thinktank.quick_response_agent = create_quick_response_agent("test-model")
        crew = MagicMock()
        crew.kickoff.return_value = "Hello! How can I help?"

        with patch("main.Crew", return_value=crew) as crew_factory:
            result = thinktank.process_query("What is 2 + 2?")

        crew_factory.assert_called_once()
        self.assertEqual(crew_factory.call_args.kwargs["agents"], [thinktank.quick_response_agent])
        self.assertEqual(len(crew_factory.call_args.kwargs["tasks"]), 1)
        self.assertEqual(result.final_output, "Hello! How can I help?")
        self.assertIsNone(result.final_score)
        self.assertTrue(result.success)

    def test_complex_query_runs_full_five_stage_pipeline(self):
        from main import ThinkTank

        thinktank = ThinkTank.__new__(ThinkTank)
        thinktank.planner = MagicMock()
        thinktank.researcher = MagicMock()
        thinktank.executor = MagicMock()
        thinktank.critic = MagicMock()
        thinktank.orchestrator = MagicMock()
        thinktank.quick_response_agent = MagicMock()
        crew_results = ["plan", "research", "draft", "Overall Score: 9/10", "final answer"]

        with patch("main.Crew") as crew_factory, \
                patch("main.create_planning_task"), \
                patch("main.create_research_task"), \
                patch("main.create_execution_task"), \
                patch("main.create_critique_task"), \
                patch("main.create_orchestration_task"):
            crew_factory.return_value.kickoff.side_effect = crew_results
            result = thinktank.process_query("Research, compare, and recommend the best option with evidence")

        self.assertEqual(crew_factory.call_count, 5)
        self.assertEqual(result.final_output, "final answer")


class TestPerAgentModelConfig(unittest.TestCase):
    """Test per-agent model overrides."""

    def test_reuses_same_llm_instance_for_shared_default_model(self):
        """Multiple calls with the same provider/model should reuse a cached LLM client."""
        from main import ThinkTank

        thinktank = ThinkTank.__new__(ThinkTank)
        thinktank.provider = "google-gemini"
        thinktank.model = "gemini-1.5-flash"
        thinktank.api_key = "AIzaabcdefghijklmnopqrstuvwxyz1234567890"
        thinktank.agent_models = {}

        with patch("main.LLM") as llm_factory:
            first = thinktank._init_llm_for_model("google-gemini", "gemini-1.5-flash", "AIzaabcdefghijklmnopqrstuvwxyz1234567890")
            second = thinktank._init_llm_for_model("google-gemini", "gemini-1.5-flash", "AIzaabcdefghijklmnopqrstuvwxyz1234567890")
            third = thinktank._init_llm_for_model("google-gemini", "gemini-1.5-flash", "AIzaabcdefghijklmnopqrstuvwxyz1234567890")

        self.assertEqual(llm_factory.call_count, 1)
        self.assertIs(first, second)
        self.assertIs(second, third)

    def test_agent_models_can_be_configured_independently(self):
        from main import ThinkTank

        with patch.object(
            ThinkTank,
            "_init_llm_for_model",
            side_effect=lambda provider, model_name, api_key=None: (
                f"{provider}:{model_name}"
                if provider != "google-gemini" or model_name.startswith("gemini/")
                else f"{provider}:gemini/{model_name}"
            ),
        ) as llm_factory:
            thinktank = ThinkTank(
                provider="google-gemini",
                model_name="gemini-1.5-flash",
                api_key="AIzaabcdefghijklmnopqrstuvwxyz1234567890",
                agent_models={
                    "planner": "gemini-2.0-flash",
                    "researcher": "gemini-1.5-pro",
                },
            )

        factory_models = {call.args[1] for call in llm_factory.call_args_list}
        self.assertIn("gemini-2.0-flash", factory_models)
        self.assertIn("gemini-1.5-pro", factory_models)
        self.assertIn("gemini-1.5-flash", factory_models)
        self.assertIn("gemini-2.0-flash", str(thinktank.planner.llm.model))
        self.assertIn("gemini-1.5-pro", str(thinktank.researcher.llm.model))
        self.assertIn("gemini-1.5-flash", str(thinktank.executor.llm.model))


class TestFirestoreQueryRecord(unittest.TestCase):
    """Test suite for query persistence payload generation."""

    def test_build_query_record_generates_unique_ids(self):
        """Each saved query and result should keep separate identifiers."""
        from web_app import build_query_record

        record_a = build_query_record(
            "Explain multi-agent systems",
            "google-gemini",
            "gemini-1.5-flash",
            {"final_output": "Answer A", "final_score": 8.5, "revision_count": 1, "success": True},
        )
        record_b = build_query_record(
            "Explain multi-agent systems",
            "google-gemini",
            "gemini-1.5-flash",
            {"final_output": "Answer B", "final_score": 9.6, "revision_count": 0, "success": True},
        )

        self.assertNotEqual(record_a["query_id"], record_b["query_id"])
        self.assertNotEqual(record_a["result_id"], record_b["result_id"])
        self.assertNotEqual(record_a["query_id"], record_a["result_id"])
        self.assertEqual(record_a["query"], "Explain multi-agent systems")
        self.assertEqual(record_a["result"]["final_output"], "Answer A")


class TestHistoryPayload(unittest.TestCase):
    """Test suite for the user query history payload."""

    def test_html_template_includes_download_button(self):
        """The completed results view should expose a download action."""
        import web_app

        self.assertIn('id="downloadResultBtn"', web_app.HTML_TEMPLATE)
        self.assertIn('id="scoreMetricCard"', web_app.HTML_TEMPLATE)
        self.assertIn('id="metricsRow"', web_app.HTML_TEMPLATE)
        self.assertIn('function updateScoreMetric(score)', web_app.HTML_TEMPLATE)
        self.assertIn('function updateResultTabs(showDetails)', web_app.HTML_TEMPLATE)
        self.assertEqual(web_app.HTML_TEMPLATE.count('class="tab-btn" data-detail-tab'), 4)
        self.assertIn('Download Result', web_app.HTML_TEMPLATE)

    def test_build_history_entry_includes_query_and_result(self):
        """History records should contain the original query and final answer."""
        from web_app import build_history_entry

        record = {
            "query_id": "q-123",
            "query": "Explain multi-agent systems",
            "provider": "google-gemini",
            "model": "gemini-1.5-flash",
            "created_at": "2026-10-03T12:00:00+00:00",
            "result": {
                "final_output": "Multi-agent systems coordinate multiple specialized agents.",
                "final_score": 9.2,
                "revision_count": 1,
                "elapsed_seconds": 7.5,
                "success": True,
            },
        }

        history_entry = build_history_entry(record)

        self.assertEqual(history_entry["query_id"], "q-123")
        self.assertEqual(history_entry["query"], "Explain multi-agent systems")
        self.assertEqual(history_entry["final_output"], "Multi-agent systems coordinate multiple specialized agents.")
        self.assertEqual(history_entry["final_score"], 9.2)
        self.assertEqual(history_entry["provider"], "google-gemini")


class TestMetaModelAPI(unittest.TestCase):
    """Test Muse support through Meta's OpenAI-compatible API."""

    def test_meta_provider_uses_configured_model_and_endpoint(self):
        from main import ThinkTank

        thinktank = ThinkTank.__new__(ThinkTank)
        thinktank.provider = "meta-model-api"
        thinktank.model = "muse-spark-1.1"
        thinktank.api_key = "m" * 40

        self.assertEqual(thinktank.list_available_models("meta-model-api"), ["muse-spark-1.1"])

        with patch("main.LLM") as llm:
            thinktank._init_llm()

        self.assertEqual(llm.call_args.kwargs["base_url"], "https://api.meta.ai/v1")
        self.assertEqual(llm.call_args.kwargs["model"], "openai/muse-spark-1.1")
        self.assertEqual(llm.call_args.kwargs["api_key"], "m" * 40)
        self.assertEqual(llm.call_args.kwargs["max_tokens"], 8192)
        self.assertEqual(llm.call_args.kwargs["reasoning_effort"], "minimal")

    def test_meta_api_key_accepts_meta_key_format(self):
        from utils.key_manager import validate_api_key

        valid, message = validate_api_key("meta-model-api", "m" * 40)

        self.assertTrue(valid, message)


class TestConfiguration(unittest.TestCase):
    """Test suite for configuration management."""

    def test_config_defaults(self):
        """Test default configuration values."""
        from utils.config import Config

        self.assertIsNotNone(Config.MODEL_NAME)
        self.assertGreaterEqual(Config.TEMPERATURE, 0.0)
        self.assertLessEqual(Config.TEMPERATURE, 1.0)
        self.assertGreater(Config.MAX_TOKENS, 0)
        self.assertGreaterEqual(Config.CRITIC_PASS_THRESHOLD, 0.0)
        self.assertLessEqual(Config.CRITIC_PASS_THRESHOLD, 10.0)

    def test_config_validation(self):
        """Test configuration validation logic."""
        from utils.config import Config

        problems = Config.validate()
        self.assertIsInstance(problems, list)


if __name__ == "__main__":
    unittest.main()
