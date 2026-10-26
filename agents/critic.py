from crewai import Agent

def create_critic_agent(llm):
    return Agent(
        role='Quality Critic',
        goal='Evaluate output quality and ensure accuracy',
        backstory="""You are a rigorous quality assurance specialist who
        evaluates content for accuracy, completeness, clarity, and coherence.
        You provide scores and constructive feedback for improvement.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
