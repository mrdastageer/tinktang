# ThinkTank - Quick Start Guide

## 🎉 ThinkTank is Ready!

ThinkTank has been successfully set up and is running on your system.

## 🚀 How to Run ThinkTank

### Option 1: Web Interface (Recommended)
The Streamlit web interface is currently running at:
- **Local URL:** http://localhost:8501
- **Network URL:** http://10.69.39.94:8501

Just open your browser and navigate to http://localhost:8501

To restart the web interface:
```bash
cd C:\Users\harih\ThinkTank
source venv/Scripts/activate
streamlit run app.py
```

### Option 2: Command Line Interface (CLI)
```bash
cd C:\Users\harih\ThinkTank
source venv/Scripts/activate
python main.py
```

Then enter your queries when prompted.

## 🧠 What ThinkTank Does

ThinkTank is a Multi-Agent System where 5 specialized AI agents collaborate:

1. **📋 Planner** - Breaks down your query into subtasks
2. **🔍 Researcher** - Gathers relevant information
3. **✍️ Executor** - Creates initial draft responses
4. **🎯 Critic** - Reviews and scores quality (must score 7+/10)
5. **🎭 Orchestrator** - Finalizes the polished output

## 📝 Example Queries

Try asking ThinkTank:
- "Explain quantum computing in simple terms"
- "Write a business plan for a coffee shop"
- "Create a study guide for machine learning basics"
- "Explain blockchain technology to a 10-year-old"

## ⚙️ Configuration

Your configuration is in `.env`:
- Currently using **demo mode** (works without API keys)
- To use Google Gemini: Add your API key to `.env`
- Quality threshold: 7/10 (adjustable in `utils/config.py`)
- Max revision attempts: 3

## 🛠️ Project Structure

```
ThinkTank/
├── agents/          # Agent definitions (planner, researcher, etc.)
├── tasks/           # Task definitions for each phase
├── utils/           # Configuration and utilities
├── app.py           # Streamlit web interface
├── main.py          # CLI interface
└── .env             # Environment configuration
```

## 📊 Features

✅ Multi-agent collaboration  
✅ Automated quality assurance loop  
✅ Web + CLI interfaces  
✅ Configurable quality thresholds  
✅ Works with multiple LLM providers  

## 🔧 Troubleshooting

If you encounter issues:
1. Make sure virtual environment is activated: `source venv/Scripts/activate`
2. Check dependencies: `pip list | grep -E "crewai|streamlit"`
3. View logs: Check `thinktank.log` file
4. Restart Streamlit: Stop with Ctrl+C and run `streamlit run app.py`

## 📚 More Information

See `ThinkTank_Project_Guide.md` for detailed documentation and architecture.

---

**Created:** September 25, 2026  
**Status:** ✅ Ready to Use
