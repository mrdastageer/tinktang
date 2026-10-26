"""
Agent & Task Compatibility Layer

Provides seamless integration with CrewAI when installed,
or a 100% compatible lightweight implementation when running standalone.

A real LLM is always required. There is no simulated fallback.
"""

from typing import Any, Optional


try:
    from crewai import Agent as CrewAIAgent
    from crewai import Task as CrewAITask
    from crewai import Crew as CrewAICrew
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    CrewAIAgent = None
    CrewAITask = None
    CrewAICrew = None


class BaseAgent:
    """Lightweight Agent representation compatible with CrewAI interface."""

    def __init__(
        self,
        role: str,
        goal: str,
        backstory: str,
        llm: Any = None,
        verbose: bool = True,
        allow_delegation: bool = False,
        tools: Optional[list] = None,
        **kwargs,
    ):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        # Store LLM config - can be None for demo/testing
        # Accept either string model name or BaseLLM instance for compatibility
        self.llm = llm
        self.verbose = verbose
        self.allow_delegation = allow_delegation
        self.tools = tools or []
        self.extra = kwargs

    def __repr__(self) -> str:
        return f"Agent(role='{self.role}')"


class BaseTask:
    """Lightweight Task representation compatible with CrewAI interface."""

    def __init__(
        self,
        description: str,
        agent: Any,
        expected_output: str = "",
        **kwargs,
    ):
        self.description = description
        self.agent = agent
        self.expected_output = expected_output
        self.extra = kwargs

    def __repr__(self) -> str:
        return f"Task(agent='{getattr(self.agent, 'role', 'unknown')}', expected_output='{self.expected_output[:30]}...')"


class BaseCrew:
    """Lightweight Crew orchestrator compatible with CrewAI interface."""

    def __init__(
        self,
        agents: list,
        tasks: list,
        verbose: bool = False,
        **kwargs,
    ):
        self.agents = agents
        self.tasks = tasks
        self.verbose = verbose
        self.extra = kwargs

    def kickoff(self) -> str:
        """Executes tasks using the configured LLM. A real LLM is required."""
        outputs = []
        for task in self.tasks:
            agent = task.agent
            prompt = (
                f"You are the {agent.role}.\n"
                f"Your Goal: {agent.goal}\n"
                f"Your Backstory: {agent.backstory}\n\n"
                f"Task Description:\n{task.description}\n\n"
                f"Expected Output:\n{task.expected_output}\n"
            )

            if agent.llm and hasattr(agent.llm, "invoke"):
                response = agent.llm.invoke(prompt)
                content = getattr(response, "content", str(response))
                outputs.append(content)
            elif agent.llm and callable(agent.llm):
                outputs.append(str(agent.llm(prompt)))
            else:
                raise RuntimeError(
                    f"No LLM configured for the {agent.role}. "
                    "ThinkTank requires a valid API key; demo mode has been removed."
                )

        return "\n\n".join(outputs)


def get_agent_class():
    """Return CrewAI Agent if available, otherwise BaseAgent."""
    return CrewAIAgent if HAS_CREWAI else BaseAgent


def get_task_class():
    """Return CrewAI Task if available, otherwise BaseTask."""
    return CrewAITask if HAS_CREWAI else BaseTask


def get_crew_class():
    """Return CrewAI Crew if available, otherwise BaseCrew."""
    return CrewAICrew if HAS_CREWAI else BaseCrew
