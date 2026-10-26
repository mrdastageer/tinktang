from crewai import Agent

def create_executor_agent(llm):
    return Agent(
        role='Content Executor',
        goal='Generate high-quality content based on research',
        backstory="""You are a skilled writer and problem solver who creates
        comprehensive, well-structured content. You excel at transforming
        research into actionable outputs.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
