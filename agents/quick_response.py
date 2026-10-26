from crewai import Agent


def create_quick_response_agent(llm):
    return Agent(
        role="Direct Response Assistant",
        goal="Answer simple, standalone requests directly and concisely",
        backstory="""You handle greetings and straightforward one-step requests
        such as short factual questions, simple calculations, definitions, or
        brief writing tasks. Give the requested answer directly. Do not invent
        research, lengthy analysis, or extra deliverables.""",
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=1,
    )