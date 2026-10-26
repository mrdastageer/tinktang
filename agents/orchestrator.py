from crewai import Agent

def create_orchestrator_agent(llm):
    return Agent(
        role='Orchestrator',
        goal='Synthesize and finalize the best possible output',
        backstory="""You are the final authority who synthesizes all reviewed
        components into a cohesive, polished final output. You ensure
        consistency and completeness while delivering a clear final answer.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
