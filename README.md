# ThinkTank - Multi-Agent System

A collaborative multi-agent system where specialized AI agents work together to solve complex problems.

## Features

- **Multiple Specialized Agents**: Planner, Researcher, Executor, Critic, and Orchestrator
- **Quality Assurance Loop**: Automated critique and revision process
- **Web Interface**: User-friendly Streamlit dashboard
- **CLI Support**: Command-line interface for quick queries

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/Mac
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your AI provider keys and Firebase web app configuration
```

4. Configure Firebase Authentication:
   - Create a Firebase project and register a web app in the Firebase console.
   - In **Authentication → Sign-in method**, enable **Email/Password**.
   - Copy the web app's API key, auth domain, project ID, and app ID into the `FIREBASE_*` entries in `.env`.
   - Configure Firebase Admin credentials for the server with Google Application Default Credentials, or set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON path. Never commit that JSON file.

The login page supports email/password sign-in and account creation. The server verifies Firebase ID tokens before serving models or processing queries.

## Usage

### CLI Version
```bash
python main.py
```

### Web Interface
```bash
python web_app.py
```

## System Architecture

```
User Query → Planner → Researcher → Executor → Critic → Orchestrator → Final Output
                                        ↑           ↓
                                        └─── Loop ──┘
                                     (If score < 6)
```

## Configuration

Edit `utils/config.py` or `.env` file to adjust:
- Model parameters (temperature, max tokens)
- Quality thresholds
- Revision attempt limits

# tinktang

