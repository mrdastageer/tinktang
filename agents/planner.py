from crewai import Agent

def create_planner_agent(llm):
    return Agent(
        role='Strategic Planner',
        goal='Break down complex queries into manageable subtasks',
        backstory="""You are a master strategist who excels at analyzing
        complex problems and breaking them down into clear, actionable steps.
        You understand task dependencies and optimal execution sequences.""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )
