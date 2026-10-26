from crewai import Task


def create_quick_response_task(agent, query):
    return Task(
        description=f"Answer this simple, standalone request directly and concisely: {query}",
        agent=agent,
        expected_output="A direct answer that fulfills the request without unnecessary detail",
    )


def create_planning_task(agent, query):
    return Task(
        description=f"""Analyze the following query and break it down into
        clear subtasks: {query}

        Provide:
        1. List of subtasks
        2. Execution sequence
        3. Dependencies between tasks""",
        agent=agent,
        expected_output="Structured task breakdown with clear sequence"
    )

def create_research_task(agent, plan):
    return Task(
        description=f"""Based on this plan: {plan}

        Conduct thorough research and gather:
        1. Relevant facts and data
        2. Context and background
        3. Supporting evidence""",
        agent=agent,
        expected_output="Comprehensive research findings"
    )

def create_execution_task(agent, research):
    return Task(
        description=f"""Using this research: {research}

        Create a complete draft that:
        1. Addresses all points
        2. Is well-structured
        3. Is clear and comprehensive""",
        agent=agent,
        expected_output="Complete draft content"
    )

def create_critique_task(agent, draft):
    return Task(
        description=f"""Evaluate this draft: {draft}

        Provide:
        1. Quality score (0-10)
        2. Strengths
        3. Weaknesses
        4. Specific improvements needed

        Score below 7 requires revision.""",
        agent=agent,
        expected_output="Quality evaluation with score and feedback"
    )

def create_orchestration_task(agent, approved_content):
    return Task(
        description=f"""Synthesize this approved content: {approved_content}

        Produce a final output that is:
        1. Coherent and polished
        2. Complete and accurate
        3. Ready for delivery""",
        agent=agent,
        expected_output="Final polished output"
    )
