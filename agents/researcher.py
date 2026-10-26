from crewai import Agent

def create_researcher_agent(llm):
    return Agent(
        role='Research Specialist',
        goal='Gather comprehensive and accurate information',
        backstory="""You are a diligent researcher with expertise in finding
        relevant information, validating sources, and synthesizing knowledge
        from multiple domains.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
