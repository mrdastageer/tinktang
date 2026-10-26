"""
ThinkTank - Modern Local Web Interface with Multi-Provider Support


"""

import http.server
import json
import socketserver
import sys
import threading
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import utils.config
from utils.config import Config
from main import ThinkTank
from agents.planner import create_planner_agent
from agents.researcher import create_researcher_agent
from agents.executor import create_executor_agent
from agents.critic import create_critic_agent
from agents.orchestrator import create_orchestrator_agent

PORT = 8505
_firebase_admin_lock = threading.Lock()


def build_query_record(query, provider, model, result_payload):
    """Create a Firestore-friendly record with unique IDs for the query and result."""
    timestamp = datetime.now(timezone.utc).isoformat()
    query_id = str(uuid.uuid4())
    result_id = str(uuid.uuid4())

    record = {
        "query_id": query_id,
        "result_id": result_id,
        "query": query,
        "provider": provider,
        "model": model,
        "created_at": timestamp,
        "status": "completed" if result_payload.get("success", True) else "failed",
        "result": {
            "final_output": result_payload.get("final_output"),
            "final_score": result_payload.get("final_score"),
            "revision_count": result_payload.get("revision_count", 0),
            "elapsed_seconds": result_payload.get("elapsed_seconds", 0.0),
            "success": result_payload.get("success", True),
            "plan": result_payload.get("plan"),
            "research": result_payload.get("research"),
            "draft": result_payload.get("draft"),
            "critique": result_payload.get("critique"),
        },
    }
    return record


def build_history_entry(record):
    """Normalize a Firestore query record into a compact history entry."""
    result = record.get("result", {}) or {}
    return {
        "query_id": record.get("query_id"),
        "query": record.get("query", ""),
        "provider": record.get("provider", ""),
        "model": record.get("model", ""),
        "created_at": record.get("created_at"),
        "status": record.get("status", "completed"),
        "final_output": result.get("final_output"),
        "final_score": result.get("final_score"),
        "revision_count": result.get("revision_count", 0),
        "elapsed_seconds": result.get("elapsed_seconds", 0.0),
        "success": result.get("success", True),
    }


def fetch_user_query_history(user_uid, limit=10):
    """Fetch the most recent query records saved for a signed-in user."""
    if not Config.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is not configured on the server")

    app = ensure_firebase_admin_app()
    from firebase_admin import firestore

    database_id = Config.FIRESTORE_DATABASE_ID
    client = firestore.client(app=app, database_id=database_id) if database_id and database_id != "(default)" else firestore.client(app=app)
    user_doc = client.collection("users").document(user_uid)
    query = user_doc.collection("query_results").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
    return [build_history_entry(doc.to_dict()) for doc in query.stream()]


def ensure_firebase_admin_app():
    """Initialize the Firebase Admin SDK once so Firestore is available."""
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as error:
        raise RuntimeError("Install the firebase-admin dependency to enable Firestore storage") from error

    if not firebase_admin._apps:
        options = {"projectId": Config.FIREBASE_PROJECT_ID}
        if Config.GOOGLE_APPLICATION_CREDENTIALS:
            credential_path = Path(Config.GOOGLE_APPLICATION_CREDENTIALS).expanduser()
            if not credential_path.is_absolute():
                credential_path = Path(__file__).resolve().parent / credential_path
            options["credential"] = credentials.Certificate(str(credential_path))
        firebase_admin.initialize_app(options=options)

    return firebase_admin.get_app()


def save_query_result_to_firestore(user_uid, query, provider, model, result_payload):
    """Persist the query and final answer to Firestore under the signed-in user."""
    if not Config.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is not configured on the server")

    app = ensure_firebase_admin_app()
    from firebase_admin import firestore

    database_id = Config.FIRESTORE_DATABASE_ID
    client = firestore.client(app=app, database_id=database_id) if database_id and database_id != "(default)" else firestore.client(app=app)

    record = build_query_record(query, provider, model, result_payload)
    user_doc = client.collection("users").document(user_uid)
    user_doc.collection("query_results").document(record["query_id"]).set(record)
    user_doc.collection("results").document(record["result_id"]).set({
        "result_id": record["result_id"],
        "query_id": record["query_id"],
        "final_output": record["result"]["final_output"],
        "final_score": record["result"]["final_score"],
        "created_at": record["created_at"],
    })
    return record


def verify_firebase_id_token(id_token):
    """Verify a Firebase ID token using server-side Application Default Credentials."""
    if not Config.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is not configured on the server")

    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError as error:
        raise RuntimeError("Install the firebase-admin dependency to enable login") from error

    with _firebase_admin_lock:
        try:
            app = firebase_admin.get_app()
        except ValueError:
            try:
                options = {"projectId": Config.FIREBASE_PROJECT_ID}
                if Config.GOOGLE_APPLICATION_CREDENTIALS:
                    credential_path = Path(Config.GOOGLE_APPLICATION_CREDENTIALS).expanduser()
                    if not credential_path.is_absolute():
                        credential_path = Path(__file__).resolve().parent / credential_path
                    credential = credentials.Certificate(str(credential_path))
                    app = firebase_admin.initialize_app(credential, options=options)
                else:
                    app = firebase_admin.initialize_app(options=options)
            except Exception as error:
                raise RuntimeError(
                    "Firebase Admin credentials are unavailable; set GOOGLE_APPLICATION_CREDENTIALS to a valid service-account JSON file or configure Application Default Credentials"
                ) from error

    try:
        return auth.verify_id_token(id_token, app=app, check_revoked=True)
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError) as error:
        raise ValueError("Firebase login token is invalid or expired") from error
    except Exception as error:
        raise RuntimeError("Firebase Admin could not verify the login token") from error

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ThinkTank </title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #08121d;
            --bg-2: #0d1726;
            --panel: rgba(15, 23, 36, 0.85);
            --panel-strong: rgba(12, 19, 30, 0.95);
            --panel-soft: rgba(19, 30, 44, 0.9);
            --border: rgba(148, 163, 184, 0.18);
            --border-strong: rgba(56, 189, 248, 0.4);
            --text: #e6f1ff;
            --muted: #8aa4c4;
            --cyan: #38bdf8;
            --cyan-strong: #06b6d4;
            --violet: #a855f7;
            --green: #34d399;
            --amber: #fbbf24;
            --danger: #f87171;
            --shadow: rgba(3, 7, 18, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        html, body { height: 100%; }
        body {
            background:
                radial-gradient(circle at top left, rgba(56, 189, 248, 0.12), transparent 30%),
                radial-gradient(circle at top right, rgba(168, 85, 247, 0.12), transparent 28%),
                linear-gradient(180deg, var(--bg) 0%, var(--bg-2) 100%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .topbar {
            position: sticky;
            top: 0;
            z-index: 20;
            backdrop-filter: blur(18px);
            background: rgba(8, 18, 29, 0.76);
            border-bottom: 1px solid var(--border);
            box-shadow: 0 12px 24px rgba(0,0,0,0.18);
        }
        .header-content {
            max-width: 1440px;
            margin: 0 auto;
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }
        .brand-wrap {
            display: flex;
            align-items: center;
            gap: 0.8rem;
        }
        .brand-badge {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--cyan), var(--violet));
            box-shadow: 0 0 14px rgba(56, 189, 248, 0.9);
        }
        .header-title h1 {
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            color: #eff7ff;
        }
        .account-controls { display: flex; align-items: center; gap: 0.85rem; }
        .account-controls #signedInUser { color: var(--muted); font-size: 0.8rem; }
        .account-controls button {
            border: 1px solid rgba(148,163,184,0.3);
            border-radius: 8px;
            background: rgba(15,23,36,0.7);
            color: var(--text);
            padding: 0.5rem 0.8rem;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
        }

        .workspace-shell {
            max-width: 1440px;
            width: 100%;
            margin: 1.25rem auto 0;
            padding: 0 1.25rem 2rem;
            display: grid;
            grid-template-columns: 220px minmax(0, 1fr);
            gap: 1.25rem;
            flex: 1;
        }

        .sidebar {
            background: rgba(15, 23, 36, 0.8);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1rem 0.8rem;
            box-shadow: 0 18px 36px rgba(2,6,23,0.35);
            height: fit-content;
            position: sticky;
            top: 88px;
        }
        .sidebar-header {
            font-weight: 700;
            font-size: 0.72rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--muted);
            margin: 0.25rem 0.55rem 0.8rem;
        }
        .nav-list { display: grid; gap: 0.4rem; }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            padding: 0.72rem 0.75rem;
            border-radius: 12px;
            color: var(--muted);
            background: transparent;
            border: 1px solid transparent;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
        }
        .nav-item:hover {
            background: rgba(56, 189, 248, 0.08);
            border-color: rgba(56, 189, 248, 0.18);
            color: var(--text);
        }
        .nav-item.active {
            background: linear-gradient(135deg, rgba(56,189,248,0.12), rgba(168,85,247,0.12));
            border-color: rgba(56, 189, 248, 0.2);
            color: var(--text);
        }
        .nav-bullet {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--cyan);
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.9);
        }
        .nav-item:nth-child(2) .nav-bullet { background: var(--violet); }
        .nav-item:nth-child(3) .nav-bullet { background: var(--green); }
        .nav-item:nth-child(4) .nav-bullet { background: var(--amber); }
        .sidebar-card {
            margin-top: 1.2rem;
            background: linear-gradient(180deg, rgba(15,23,36,0.8), rgba(10,16,24,0.95));
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 0.9rem;
        }
        .mini-kpi {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 0.8rem;
            font-size: 0.76rem;
            color: var(--muted);
        }
        .mini-kpi strong { color: var(--text); font-size: 0.9rem; }

        .container {
            width: 100%;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .view-section {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            width: 100%;
        }

        .hero-panel {
            padding: 1.2rem 1.3rem;
            background: linear-gradient(180deg, rgba(12, 19, 30, 0.94), rgba(19, 30, 44, 0.92));
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: 0 22px 36px rgba(2,6,23,0.3);
        }
        .hero-panel h2 {
            font-size: 1.2rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }
        .hero-panel p {
            color: var(--muted);
            font-size: 0.85rem;
            line-height: 1.6;
        }
        .hero-grid {
            margin-top: 1rem;
            display: grid;
            grid-template-columns: repeat(4, minmax(120px, 1fr));
            gap: 0.75rem;
        }
        .stat-card {
            background: rgba(15, 23, 36, 0.68);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.8rem;
        }
        .stat-card .label {
            color: var(--muted);
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .stat-card .value {
            margin-top: 0.45rem;
            font-size: 1.2rem;
            font-weight: 800;
            color: var(--text);
        }
        .stat-card .delta {
            margin-top: 0.2rem;
            font-size: 0.72rem;
            color: var(--green);
        }

        .config-card, .card {
            background: rgba(15, 23, 36, 0.78);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1.15rem;
            box-shadow: 0 18px 30px rgba(4, 7, 18, 0.18);
        }
        .config-header {
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 0.8rem;
            color: #edf7ff;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }
        .config-header span:last-child {
            color: var(--muted);
            font-size: 0.72rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-weight: 700;
        }
        .config-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
        .form-group { display: flex; flex-direction: column; gap: 0.38rem; }
        .form-group label { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
        .form-control {
            padding: 0.72rem 0.8rem;
            border: 1px solid var(--border);
            border-radius: 10px;
            font-size: 0.9rem;
            outline: none;
            background: rgba(9, 15, 22, 0.8);
            color: var(--text);
        }
        .form-control:focus { border-color: var(--border-strong); box-shadow: 0 0 0 3px rgba(56,189,248,0.18); }
        .agent-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }

        .agents-strip {
            display: grid;
            grid-template-columns: repeat(5, minmax(130px, 1fr));
            gap: 0.8rem;
        }
        .agent-card {
            background: linear-gradient(180deg, rgba(15,23,36,0.82), rgba(10,17,27,0.92));
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 0.95rem 0.75rem;
            text-align: center;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .agent-icon { font-size: 1.5rem; margin-bottom: 0.3rem; }
        .agent-name { font-weight: 700; color: var(--text); }
        .agent-desc { color: var(--muted); font-size: 0.72rem; margin-top: 0.18rem; margin-bottom: 0.5rem; }
        .agent-card select.form-control {
            width: 100%;
            padding: 0.5rem;
            font-size: 0.78rem;
            text-overflow: ellipsis;
            white-space: nowrap;
            overflow: hidden;
        }

        .card { padding: 1.2rem; }
        .input-group { display: flex; flex-direction: column; gap: 0.8rem; }
        textarea {
            width: 100%;
            height: 110px;
            padding: 0.9rem 1rem;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: rgba(9, 15, 22, 0.75);
            color: var(--text);
            font-size: 0.96rem;
            resize: vertical;
            outline: none;
        }
        textarea:focus { border-color: var(--border-strong); box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18); }

        .action-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.8rem; }
        .quick-tags { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .quick-btn {
            background: rgba(17, 24, 39, 0.82);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 0.45rem 0.75rem;
            font-size: 0.73rem;
            color: var(--muted);
            cursor: pointer;
        }
        .quick-btn:hover { border-color: rgba(56,189,248,0.35); color: var(--text); }

        .btn-primary {
            background: linear-gradient(135deg, var(--cyan), var(--violet));
            color: #03111b;
            border: none;
            padding: 0.8rem 1.4rem;
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.92rem;
            cursor: pointer;
            box-shadow: 0 10px 18px rgba(56,189,248,0.22);
        }
        .btn-primary:disabled { opacity: 0.55; cursor: not-allowed; }

        .progress-box {
            display: none;
            margin-top: 1rem;
            background: linear-gradient(180deg, rgba(11, 22, 34, 0.95), rgba(8, 15, 25, 0.95));
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 16px;
            padding: 1.2rem;
            box-shadow: 0 12px 28px rgba(0,0,0,0.3);
        }
        .progress-box.active { display: block; }
        .progress-header {
            font-weight: 700;
            margin-bottom: 1rem;
            color: #7dd3fc;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            font-size: 0.95rem;
        }
        .step-list { display: flex; flex-direction: column; gap: 0.6rem; }
        .step-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.88rem;
            color: var(--muted);
            padding: 0.55rem 0.8rem;
            border-radius: 10px;
            background: rgba(15, 23, 36, 0.4);
            border: 1px solid transparent;
            transition: all 0.25s ease;
        }
        .step-item.active {
            color: #f0f9ff;
            background: rgba(56, 189, 248, 0.12);
            border-color: rgba(56, 189, 248, 0.35);
            font-weight: 600;
        }
        .step-item.completed {
            color: var(--green);
            background: rgba(52, 211, 153, 0.06);
            border-color: rgba(52, 211, 153, 0.2);
        }
        .step-status-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 20px;
            height: 20px;
            font-size: 0.85rem;
        }
        .step-model-badge {
            margin-left: auto;
            font-size: 0.72rem;
            color: var(--cyan);
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.25);
            padding: 0.2rem 0.55rem;
            border-radius: 6px;
            font-family: monospace;
            max-width: 220px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(56, 189, 248, 0.3);
            border-top-color: var(--cyan);
            border-radius: 50%;
            animation: spin 0.7s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .results-box { display: none; }
        .results-box.active { display: block; }
        .metrics-row { display: grid; grid-template-columns: repeat(4, minmax(100px, 1fr)); gap: 0.8rem; margin-bottom: 1.1rem; }
        .metrics-row.without-score { grid-template-columns: repeat(3, minmax(100px, 1fr)); }
        .metrics-row[hidden] { display: none; }
        .metric-card { background: rgba(10, 16, 24, 0.7); border: 1px solid var(--border); border-radius: 12px; padding: 0.75rem; text-align: center; }
        .metric-card[hidden] { display: none; }
        .metric-val { font-size: 1.3rem; font-weight: 800; color: var(--text); }
        .metric-label { font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-top: 0.25rem; }
        .score-green { color: var(--green); }

        .results-actions { display: flex; justify-content: flex-end; margin-bottom: 1rem; }
        .download-btn { background: rgba(9, 27, 25, 0.9); border: 1px solid rgba(52,211,153,0.4); color: var(--green); border-radius: 10px; padding: 0.7rem 1rem; font-weight: 700; cursor: pointer; }
        .download-btn:hover:not(:disabled) { background: rgba(11, 36, 32, 0.98); }
        .download-btn:disabled { opacity: 0.45; cursor: not-allowed; }

        .tabs { display: flex; border-bottom: 1px solid var(--border); margin-bottom: 1rem; gap: 0.5rem; overflow-x: auto; }
        .tabs [hidden], .tab-content[hidden] { display: none; }
        .tab-btn { background: transparent; border: none; padding: 0.7rem 0.9rem; font-size: 0.82rem; font-weight: 700; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap; }
        .tab-btn.active { color: var(--text); border-bottom-color: var(--cyan); }

        .tab-content {
            display: none;
            background: rgba(9, 15, 22, 0.75);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            white-space: pre-wrap;
            line-height: 1.7;
            max-height: 420px;
            overflow-y: auto;
            color: #e2edf9;
        }
        .tab-content.active { display: block; }

        .history-list { display: grid; gap: 0.75rem; }
        .saved-session-list { display: grid; gap: 0.5rem; max-width: 100%; min-width: 0; }
        .history-item {
            display: block;
            width: 100%;
            box-sizing: border-box;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            background: rgba(9, 15, 22, 0.6);
            cursor: pointer;
            transition: 0.2s ease;
            overflow: hidden;
            text-align: left;
            min-width: 0;
        }
        .history-item:hover { border-color: rgba(56,189,248,0.4); background: rgba(13, 22, 34, 0.8); }
        .saved-session-list .history-item { padding: 0.65rem 0.75rem; }
        .history-topline { display: flex; justify-content: space-between; gap: 0.75rem; align-items: center; margin-bottom: 0.4rem; flex-wrap: wrap; min-width: 0; }
        .history-query {
            font-weight: 700;
            color: var(--text);
            min-width: 0;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        .history-meta { font-size: 0.72rem; color: var(--muted); }
        .history-preview {
            font-size: 0.8rem;
            color: #dbeafc;
            line-height: 1.5;
            max-height: 3.4em;
            overflow: hidden;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        .history-empty { color: var(--muted); font-size: 0.84rem; padding: 0.4rem 0; }

        .auth-gate { position: fixed; inset: 0; z-index: 30; display: grid; place-items: center; padding: 1rem; background: rgba(3,7,18,0.76); backdrop-filter: blur(10px); }
        .auth-gate[hidden] { display: none; }
        .auth-panel {
            width: min(420px, 100%);
            padding: 1.5rem;
            border: 1px solid var(--border);
            border-radius: 18px;
            background: rgba(11, 17, 27, 0.94);
            box-shadow: 0 20px 42px rgba(0,0,0,0.35);
        }
        .auth-panel h2 { margin-bottom: 0.5rem; font-size: 1.45rem; }
        .auth-panel p { margin-bottom: 1rem; color: var(--muted); font-size: 0.9rem; }
        .auth-form { display: grid; gap: 0.8rem; }
        .auth-form input {
            width: 100%;
            padding: 0.8rem 0.9rem;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: rgba(9,15,22,0.7);
            color: var(--text);
            font-size: 0.95rem;
        }
        .auth-form button, .auth-switch { min-height: 42px; border-radius: 10px; cursor: pointer; font-weight: 700; }
        .auth-form button { background: linear-gradient(135deg, var(--cyan), var(--violet)); color: #02101d; border: none; }
        .auth-switch { margin-top: 0.75rem; background: transparent; border: 1px solid var(--border); color: var(--text); }
        .auth-divider { margin: 1rem 0; color: var(--muted); text-align: center; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; }
        .auth-google { width: 100%; min-height: 42px; border-radius: 10px; background: rgba(10, 16, 24, 0.85); border: 1px solid var(--border); color: var(--text); cursor: pointer; font-weight: 700; }
        .auth-google:disabled { opacity: 0.5; cursor: not-allowed; }
        .auth-status { min-height: 1.3em; margin-top: 0.75rem !important; color: #fca5a5 !important; }

        footer { text-align: center; padding: 1.2rem; color: var(--muted); font-size: 0.8rem; }

        @media (max-width: 1100px) {
            .workspace-shell { grid-template-columns: 1fr; }
            .sidebar { position: static; }
            .agents-strip { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
        }

        @media (max-width: 720px) {
            .header-content { flex-wrap: wrap; }

            .config-grid, .metrics-row, .hero-grid { grid-template-columns: 1fr; }
            .agents-strip { grid-template-columns: 1fr; }
            .action-row { align-items: stretch; }
            .quick-tags { width: 100%; }
            .btn-primary { width: 100%; justify-content: center; }
        }
    </style>
</head>
<body>

<header class="topbar">
    <div class="header-content">
        <div class="brand-wrap">
            <span class="brand-badge"></span>
            <div class="header-title">
                <h1>ThinkTank</h1>
            </div>
        </div>

        <div class="account-controls">
            <span id="signedInUser"></span>
            <button id="signOutButton" type="button" hidden>Sign out</button>
        </div>
    </div>
</header>

<section id="authGate" class="auth-gate" aria-labelledby="authTitle">
    <div class="auth-panel">
        <h2 id="authTitle">Sign in to ThinkTank</h2>
        <p>Use your Firebase Authentication account to continue.</p>
        <form id="authForm" class="auth-form">
            <input id="authEmail" type="email" autocomplete="email" placeholder="Email address" required>
            <input id="authPassword" type="password" autocomplete="current-password" placeholder="Password" minlength="6" required>
            <button id="authSubmit" type="submit">Sign in</button>
        </form>
        <div class="auth-divider">or</div>
        <button id="googleSignInButton" class="auth-google" type="button">Continue with Google</button>
        <button id="authModeButton" class="auth-switch" type="button">Create an account</button>
        <p id="authStatus" class="auth-status" role="status" aria-live="polite"></p>
    </div>
</section>

<div class="workspace-shell">
    <aside class="sidebar">
        <div class="sidebar-header">Workspace</div>
        <div class="nav-list">
            <div class="nav-item active" id="activePipelinesNav" role="button" tabindex="0" aria-controls="progressBox"><span class="nav-bullet"></span> Active Pipelines</div>
            <div class="nav-item" id="savedSessionsNav" role="button" tabindex="0" aria-controls="savedSessionsList"><span class="nav-bullet"></span> Saved Sessions</div>
        </div>


    </aside>

    <div class="container">

    <!-- Active Pipelines View -->
    <div id="activePipelinesView" class="view-section">

    <!-- Model Provider & Key Configuration -->
    <div class="config-card">
        <div class="config-header">
            <span>⚙️ LLM Provider & Model Selection</span>
           
        </div>
        <div class="config-grid">
            <div class="form-group">
                <label>Provider</label>
                <select id="providerSelect" class="form-control" onchange="updateModelOptions()">
                    <option value="nvidia-nim" selected>NVIDIA</option>
                    <option value="google-gemini">Google Gemini </option>
                    <option value="omniroute">OmniRoute</option>
                    <option value="meta-model-api">Muse by Meta</option>
                </select>
            </div>
            <div class="form-group">
                <label>Model Architecture</label>
                <select id="modelSelect" class="form-control">
                    <!-- Populated dynamically -->
                </select>
            </div>
        </div>
    </div>

    <!-- Agent Configuration -->
    <div class="config-card" style="margin-top: 1rem;">
        <div class="config-header">
            <span>🧠 Agent Configuration</span>
            <span style="font-size: 0.75rem; color: #7c3aed; font-weight: 500;">Choose a model for each agent in your pipeline</span>
        </div>
        <div class="agents-strip">
            <div class="agent-card">
                <div class="agent-icon">📋</div>
                <div class="agent-name">Planner</div>
                <div class="agent-desc">Task Breakdown</div>
                <select id="plannerModelSelect" class="form-control" style="margin-top: 0.75rem; font-size: 0.8rem;"></select>
            </div>
            <div class="agent-card">
                <div class="agent-icon">🔍</div>
                <div class="agent-name">Researcher</div>
                <div class="agent-desc">Knowledge Retrieval</div>
                <select id="researcherModelSelect" class="form-control" style="margin-top: 0.75rem; font-size: 0.8rem;"></select>
            </div>
            <div class="agent-card">
                <div class="agent-icon">✍️</div>
                <div class="agent-name">Executor</div>
                <div class="agent-desc">Drafting Engine</div>
                <select id="executorModelSelect" class="form-control" style="margin-top: 0.75rem; font-size: 0.8rem;"></select>
            </div>
            <div class="agent-card">
                <div class="agent-icon">🎯</div>
                <div class="agent-name">Critic</div>
                <div class="agent-desc">Scoring & QA (0-10)</div>
                <select id="criticModelSelect" class="form-control" style="margin-top: 0.75rem; font-size: 0.8rem;"></select>
            </div>
            <div class="agent-card">
                <div class="agent-icon">🎭</div>
                <div class="agent-name">Orchestrator</div>
                <div class="agent-desc">Final Polish</div>
                <select id="orchestratorModelSelect" class="form-control" style="margin-top: 0.75rem; font-size: 0.8rem;"></select>
            </div>
        </div>
    </div>

    <!-- Query Box -->
    <div class="card">
        <div class="input-group">
            <label for="queryInput" style="font-weight: 600; font-size: 0.95rem;">Enter your query or research problem:</label>
            <textarea id="queryInput" placeholder="e.g. Compare Multi-Agent Systems with monolithic AI architectures in terms of bias reduction and fault tolerance."></textarea>

            <div class="action-row">
                <div class="quick-tags">
                    <span style="font-size: 0.8rem; color: #64748b; margin-right: 0.2rem;">Quick Prompts:</span>
                    <button class="quick-btn" onclick="setQuery('Explain how Multi-Agent Systems solve the problem of single-model bias in AI.')">AI Bias & MAS</button>
                    <button class="quick-btn" onclick="setQuery('Design a resilient microservices architecture for an e-commerce platform.')">Microservices</button>
                    <button class="quick-btn" onclick="setQuery('Explain the principles of Zero-Trust Network Architecture.')">Zero-Trust</button>
                    <button class="quick-btn" onclick="setQuery('Explain how MetaGPT and Blackboard architectures enable autonomous AI coordination.')">MetaGPT & Blackboard</button>
                </div>
                <button class="btn-primary" id="runBtn" onclick="submitQuery()">
                    <span>🚀 Run ThinkTank</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Progress Indicator -->
    <div class="progress-box" id="progressBox">
        <div class="progress-header">
            <div class="spinner"></div> ThinkTank Agents Collaborating in Real-Time...
        </div>
        <div class="step-list" id="stepList"></div>
    </div>

    <!-- Results Area -->
    <div class="results-box card" id="resultsBox">
        <div class="metrics-row" id="metricsRow">
            <div class="metric-card" id="scoreMetricCard">
                <div class="metric-val score-green" id="scoreVal">8.7 / 10</div>
                <div class="metric-label">Quality Score</div>
            </div>
            <div class="metric-card">
                <div class="metric-val" id="revVal">0</div>
                <div class="metric-label">Revision Cycles</div>
            </div>
            <div class="metric-card">
                <div class="metric-val" id="timeVal">1.2s</div>
                <div class="metric-label">Execution Time</div>
            </div>
            <div class="metric-card">
                <div class="metric-val" id="modelBadge" style="color: #2563eb; font-size: 0.95rem; line-height: 1.8;">meta/llama-3.1-8b</div>
                <div class="metric-label">Active Model</div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" data-tab-name="final" onclick="showTab('final')">🎭 Final Synthesized Deliverable</button>
            <button class="tab-btn" data-detail-tab data-tab-name="plan" onclick="showTab('plan')">📋 Planner Breakdown</button>
            <button class="tab-btn" data-detail-tab data-tab-name="research" onclick="showTab('research')">🔍 Research Notes</button>
            <button class="tab-btn" data-detail-tab data-tab-name="draft" onclick="showTab('draft')">✍️ Executor Draft</button>
            <button class="tab-btn" data-detail-tab data-tab-name="critique" onclick="showTab('critique')">🎯 Critic Evaluation</button>
        </div>

        <div class="results-actions">
            <button id="downloadResultBtn" class="download-btn" type="button" onclick="downloadCurrentResult()" disabled>Download Result</button>
        </div>

        <div id="tab-final" class="tab-content active"></div>
        <div id="tab-plan" class="tab-content" data-detail-content></div>
        <div id="tab-research" class="tab-content" data-detail-content></div>
        <div id="tab-draft" class="tab-content" data-detail-content></div>
        <div id="tab-critique" class="tab-content" data-detail-content></div>
    </div>


    </div>

    <!-- Saved Sessions View -->
    <div id="savedSessionsView" class="view-section" style="display: none;">
        <div class="hero-panel">
            <h2>📁 Saved Sessions</h2>
            <p>View and reload previous query executions stored in Firebase.</p>
        </div>
        
        <div id="savedSessionsList" class="history-list" style="margin-top: 1rem;">
            <div class="history-empty">Loading saved sessions...</div>
        </div>
    </div>

</div>



<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-auth-compat.js"></script>
<script>
let firebaseAuth = null;
let createAccountMode = false;

function formatAuthErrorMessage(error) {
    const code = error && error.code ? error.code : '';
    const messageMap = {
        'auth/invalid-email': 'Please enter a valid email address.',
        'auth/user-disabled': 'This account has been disabled.',
        'auth/user-not-found': 'No account found for that email.',
        'auth/wrong-password': 'Incorrect password.',
        'auth/invalid-credential': 'Incorrect email or password.',
        'auth/email-already-in-use': 'An account with this email already exists.',
        'auth/weak-password': 'Your password is too weak. Use at least 6 characters.',
        'auth/network-request-failed': 'Network error. Please try again.',
        'auth/too-many-requests': 'Too many attempts. Please try again later.',
        'auth/requires-recent-login': 'Please sign in again and try once more.'
    };

    return messageMap[code] || (error && error.message ? error.message : 'Authentication failed. Please try again.');
}

async function initializeFirebaseAuth() {
    const status = document.getElementById('authStatus');
    try {
        const response = await fetch('/api/firebase-config');
        const data = await response.json();
        if (!response.ok || !data.configured) {
            throw new Error(data.error || 'Firebase web configuration is missing on the server.');
        }

        firebase.initializeApp(data.firebase_config);
        firebaseAuth = firebase.auth();
        firebaseAuth.onAuthStateChanged(async user => {
            document.getElementById('authGate').hidden = Boolean(user);
            document.getElementById('signedInUser').textContent = user ? (user.email || user.displayName || 'Signed in') : '';
            document.getElementById('signOutButton').hidden = !user;
            if (user) {
                await updateModelOptions();
                await loadUserHistory();
            } else if (document.getElementById('savedSessionsList')) {
                document.getElementById('savedSessionsList').innerHTML = '<div class="history-empty">Sign in to view your saved sessions.</div>';
            }
        });
    } catch (error) {
        status.textContent = error.message;
        document.getElementById('authSubmit').disabled = true;
        document.getElementById('googleSignInButton').disabled = true;
        document.getElementById('authModeButton').disabled = true;
    }
}

document.getElementById('authForm').addEventListener('submit', async event => {
    event.preventDefault();
    const email = document.getElementById('authEmail').value.trim();
    const password = document.getElementById('authPassword').value;
    const status = document.getElementById('authStatus');
    const submit = document.getElementById('authSubmit');
    status.textContent = '';
    submit.disabled = true;
    try {
        if (createAccountMode) {
            await firebaseAuth.createUserWithEmailAndPassword(email, password);
        } else {
            await firebaseAuth.signInWithEmailAndPassword(email, password);
        }
    } catch (error) {
        status.textContent = formatAuthErrorMessage(error);
    } finally {
        submit.disabled = false;
    }
});

document.getElementById('authModeButton').addEventListener('click', () => {
    createAccountMode = !createAccountMode;
    document.getElementById('authTitle').textContent = createAccountMode ? 'Create a ThinkTank account' : 'Sign in to ThinkTank';
    document.getElementById('authSubmit').textContent = createAccountMode ? 'Create account' : 'Sign in';
    document.getElementById('authPassword').autocomplete = createAccountMode ? 'new-password' : 'current-password';
    document.getElementById('authModeButton').textContent = createAccountMode ? 'Back to sign in' : 'Create an account';
});

document.getElementById('googleSignInButton').addEventListener('click', async () => {
    const status = document.getElementById('authStatus');
    const button = document.getElementById('googleSignInButton');
    status.textContent = '';
    button.disabled = true;
    try {
        const provider = new firebase.auth.GoogleAuthProvider();
        await firebaseAuth.signInWithPopup(provider);
    } catch (error) {
        status.textContent = formatAuthErrorMessage(error);
    } finally {
        button.disabled = false;
    }
});

document.getElementById('signOutButton').addEventListener('click', () => firebaseAuth.signOut());

async function getAuthHeaders() {
    if (!firebaseAuth || !firebaseAuth.currentUser) throw new Error('Please sign in first.');
    return { Authorization: `Bearer ${await firebaseAuth.currentUser.getIdToken()}` };
}

function populateModelSelect(select, modelOptions, defaultModel) {
    select.innerHTML = '';
    if (!modelOptions.length) {
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = 'No models available';
        select.appendChild(emptyOption);
        return;
    }

    modelOptions.forEach(modelId => {
        const option = document.createElement('option');
        option.value = modelId;
        option.textContent = modelId;
        select.appendChild(option);
    });

    if (defaultModel && modelOptions.includes(defaultModel)) {
        select.value = defaultModel;
    } else {
        select.value = modelOptions[0];
    }
}

const PROVIDER_ORDER = ['google-gemini', 'nvidia-nim', 'omniroute', 'meta-model-api'];
let mergedModelCatalog = {};
let mergedModelProviderMap = {};

async function loadMergedModelCatalog() {
    const catalog = {};
    const providerMap = {};

    for (const provider of PROVIDER_ORDER) {
        try {
            const response = await fetch(`/api/models?provider=${encodeURIComponent(provider)}`, {
                headers: await getAuthHeaders()
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load models');
            const models = Array.isArray(data.models) ? data.models : [];
            catalog[provider] = models;
            models.forEach(modelId => {
                providerMap[modelId] = provider;
            });
        } catch (error) {
            catalog[provider] = [];
        }
    }

    mergedModelCatalog = catalog;
    mergedModelProviderMap = providerMap;
    return catalog;
}

async function updateModelOptions() {
    const provider = document.getElementById('providerSelect').value;
    const modelSelect = document.getElementById('modelSelect');
    modelSelect.innerHTML = '';
    modelSelect.disabled = true;

    const loadingOption = document.createElement('option');
    loadingOption.value = '';
    loadingOption.textContent = 'Loading models...';
    modelSelect.appendChild(loadingOption);

    try {
        const catalog = await loadMergedModelCatalog();
        const modelOptions = Array.from(new Set(Object.values(catalog).flat()));
        const defaultModel = catalog[provider]?.[0] || modelOptions[0] || '';
        modelSelect.innerHTML = '';
        populateModelSelect(modelSelect, modelOptions, defaultModel);

        const agentSelectIds = [
            'plannerModelSelect',
            'researcherModelSelect',
            'executorModelSelect',
            'criticModelSelect',
            'orchestratorModelSelect',
        ];
        agentSelectIds.forEach(agentId => {
            const select = document.getElementById(agentId);
            if (select) populateModelSelect(select, modelOptions, defaultModel);
        });

        if (modelSelect.value && mergedModelProviderMap[modelSelect.value]) {
            document.getElementById('providerSelect').value = mergedModelProviderMap[modelSelect.value];
        }
    } catch (error) {
        modelSelect.innerHTML = '';
        const errorOption = document.createElement('option');
        errorOption.value = '';
        errorOption.textContent = `Could not load models: ${error.message}`;
        modelSelect.appendChild(errorOption);
    }

    modelSelect.disabled = modelSelect.options.length === 0 || !modelSelect.value;
}

function getSelectedAgentModels() {
    const agentNames = ['planner', 'researcher', 'executor', 'critic', 'orchestrator'];
    const mapping = {};
    for (const agentName of agentNames) {
        const select = document.getElementById(`${agentName}ModelSelect`);
        if (select && select.value) {
            mapping[agentName] = select.value;
        }
    }
    return mapping;
}

initializeFirebaseAuth();

function selectWorkspaceSection(navId, viewName) {
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    const navItem = document.getElementById(navId);
    if (navItem) navItem.classList.add('active');
    
    // Hide all views
    const activePipelinesView = document.getElementById('activePipelinesView');
    const savedSessionsView = document.getElementById('savedSessionsView');
    
    if (viewName === 'activePipelines') {
        if (activePipelinesView) activePipelinesView.style.display = 'flex';
        if (savedSessionsView) savedSessionsView.style.display = 'none';
    } else if (viewName === 'savedSessions') {
        if (activePipelinesView) activePipelinesView.style.display = 'none';
        if (savedSessionsView) savedSessionsView.style.display = 'block';
        loadUserHistory();
    }
}

function bindWorkspaceNavigation() {
    const activePipelinesNav = document.getElementById('activePipelinesNav');
    const savedSessionsNav = document.getElementById('savedSessionsNav');
    const bindings = [
        [activePipelinesNav, 'activePipelinesNav', 'activePipelines'],
        [savedSessionsNav, 'savedSessionsNav', 'savedSessions'],
    ];

    bindings.forEach(([navItem, navId, targetId]) => {
        if (!navItem) return;
        navItem.addEventListener('click', () => selectWorkspaceSection(navId, targetId));
        navItem.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                selectWorkspaceSection(navId, targetId);
            }
        });
    });
}

bindWorkspaceNavigation();

function setQuery(text) {
    document.getElementById('queryInput').value = text;
}

function renderHistoryResult(entry) {
    // Switch to Active Pipelines view to show the result
    selectWorkspaceSection('activePipelinesNav', 'activePipelines');
    
    document.getElementById('queryInput').value = entry.query || '';
    document.getElementById('resultsBox').classList.add('active');
    const finalOutput = entry.final_output || 'No final output saved for this query.';
    updateScoreMetric(entry.final_score);
    updateResultTabs(entry.final_score !== null && entry.final_score !== undefined);
    document.getElementById('revVal').textContent = entry.revision_count || 0;
    document.getElementById('timeVal').textContent = (entry.elapsed_seconds || 0).toFixed(1) + 's';
    document.getElementById('modelBadge').textContent = entry.model || 'Saved model';

    document.getElementById('tab-final').textContent = finalOutput;
    document.getElementById('tab-plan').textContent = 'History view does not include planner details for this saved entry.';
    document.getElementById('tab-research').textContent = 'History view does not include research notes for this saved entry.';
    document.getElementById('tab-draft').textContent = 'History view does not include executor draft details for this saved entry.';
    document.getElementById('tab-critique').textContent = 'History view does not include critic notes for this saved entry.';
    document.getElementById('providerSelect').value = entry.provider || document.getElementById('providerSelect').value;
    updateDownloadButtonState(finalOutput);
}

function updateScoreMetric(score) {
    const scoreCard = document.getElementById('scoreMetricCard');
    const hasScore = score !== null && score !== undefined && score !== '' && Number.isFinite(Number(score));
    scoreCard.hidden = !hasScore;
    scoreCard.closest('.metrics-row').classList.toggle('without-score', !hasScore);
    if (hasScore) {
        document.getElementById('scoreVal').textContent = Number(score).toFixed(1) + ' / 10';
    }
}

function updateResultTabs(showDetails) {
    document.getElementById('metricsRow').hidden = !showDetails;
    document.querySelectorAll('[data-detail-tab]').forEach(tab => { tab.hidden = !showDetails; });
    document.querySelectorAll('[data-detail-content]').forEach(tab => {
        tab.hidden = !showDetails;
        if (!showDetails) tab.classList.remove('active');
    });

    if (!showDetails) {
        document.querySelectorAll('.tab-btn').forEach(tab => tab.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
        document.querySelector('.tabs .tab-btn').classList.add('active');
        document.getElementById('tab-final').classList.add('active');
    }
}

function updateDownloadButtonState(content) {
    const button = document.getElementById('downloadResultBtn');
    const hasContent = Boolean((content || '').trim());
    button.disabled = !hasContent;
}

function downloadCurrentResult() {
    const finalText = document.getElementById('tab-final').textContent.trim();
    if (!finalText) {
        alert('There is no result available to download yet.');
        return;
    }

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const fileName = `thinktank-result-${timestamp}.txt`;
    const blob = new Blob([finalText], { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function renderHistoryEntries(entries, targetList, emptyMessage) {
    targetList.innerHTML = '';

    if (!entries.length) {
        targetList.innerHTML = `<div class="history-empty">${emptyMessage}</div>`;
        return;
    }

    entries.forEach(entry => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'history-item';
        item.style.width = '100%';
        item.style.textAlign = 'left';
        item.addEventListener('click', () => renderHistoryResult(entry));

        const date = entry.created_at ? new Date(entry.created_at).toLocaleString() : 'Unknown date';
        const preview = entry.final_output ? String(entry.final_output).slice(0, 160) : 'No final result saved.';
        item.innerHTML = `
            <div class="history-topline">
                <div class="history-query">${(entry.query || 'Untitled query').slice(0, 64)}</div>
                <div class="history-meta">${entry.final_score !== null && entry.final_score !== undefined ? Number(entry.final_score).toFixed(1) + '/10' : '—'}</div>
            </div>
            <div class="history-meta">${date} • ${entry.provider || 'unknown'} • ${entry.model || 'N/A'}</div>
            <div class="history-preview">${preview}</div>
        `;
        targetList.appendChild(item);
    });
}

async function loadUserHistory() {
    const historyList = document.getElementById('historyList');
    const savedSessionsList = document.getElementById('savedSessionsList');

    if (historyList) {
        historyList.innerHTML = '<div class="history-empty">Loading recent queries...</div>';
    }
    if (savedSessionsList) {
        savedSessionsList.innerHTML = '<div class="history-empty">Loading saved sessions...</div>';
    }

    try {
        const res = await fetch('/api/history', { headers: await getAuthHeaders() });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not load history');

        const entries = Array.isArray(data.history) ? data.history : [];
        if (historyList) {
            renderHistoryEntries(entries, historyList, 'No saved queries yet. Run your first ThinkTank workflow to create history.');
        }
        if (savedSessionsList) {
            renderHistoryEntries(entries, savedSessionsList, 'No saved sessions yet. Run a workflow to create one.');
        }
    } catch (error) {
        if (historyList) {
            historyList.innerHTML = '<div class="history-empty" style="color: #b91c1c;">' + error.message + '</div>';
        }
        if (savedSessionsList) {
            savedSessionsList.innerHTML = '<div class="history-empty" style="color: #b91c1c;">' + error.message + '</div>';
        }
    }
}

function showTab(name) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    const trigger = document.querySelector(`.tab-btn[data-tab-name="${name}"]`);
    if (trigger) trigger.classList.add('active');
    const target = document.getElementById('tab-' + name);
    if (target) target.classList.add('active');
}

function getShortModelName(modelName) {
    if (!modelName) return 'default';
    const parts = modelName.split('/');
    return parts.length > 1 ? parts[parts.length - 1] : modelName;
}

async function submitQuery() {
    const query = document.getElementById('queryInput').value.trim();
    if (!query) { alert('Please enter a query'); return; }

    const model = document.getElementById('modelSelect').value;
    const provider = mergedModelProviderMap[model] || document.getElementById('providerSelect').value;
    const agent_models = getSelectedAgentModels();

    const plannerModel = agent_models.planner || model;
    const researcherModel = agent_models.researcher || model;
    const executorModel = agent_models.executor || model;
    const criticModel = agent_models.critic || model;
    const orchestratorModel = agent_models.orchestrator || model;

    const runBtn = document.getElementById('runBtn');
    const progressBox = document.getElementById('progressBox');
    const stepList = document.getElementById('stepList');
    const resultsBox = document.getElementById('resultsBox');

    runBtn.disabled = true;
    resultsBox.classList.remove('active');
    progressBox.classList.add('active');
    stepList.innerHTML = '';

    const stages = [
        {
            icon: '📋',
            phase: 'Phase 1/5',
            agent: 'Planner Agent',
            action: 'decomposing query into execution plan',
            model: getShortModelName(plannerModel)
        },
        {
            icon: '🔍',
            phase: 'Phase 2/5',
            agent: 'Research Specialist',
            action: 'retrieving domain knowledge & context',
            model: getShortModelName(researcherModel)
        },
        {
            icon: '✍️',
            phase: 'Phase 3/5',
            agent: 'Executor Agent',
            action: 'formulating structured draft deliverable',
            model: getShortModelName(executorModel)
        },
        {
            icon: '🎯',
            phase: 'Phase 4/5',
            agent: 'Quality Critic',
            action: 'conducting multi-criteria scoring & QA',
            model: getShortModelName(criticModel)
        },
        {
            icon: '🎭',
            phase: 'Phase 5/5',
            agent: 'Orchestrator Agent',
            action: 'synthesizing final publication deliverable',
            model: getShortModelName(orchestratorModel)
        }
    ];

    const stageElements = stages.map((st, idx) => {
        const item = document.createElement('div');
        item.className = 'step-item';
        item.id = `step-item-${idx}`;
        item.innerHTML = `
            <span class="step-status-icon" id="step-icon-${idx}">${st.icon}</span>
            <span><strong>[${st.phase}] ${st.agent}</strong> ${st.action}...</span>
            <span class="step-model-badge" title="${st.model}">🤖 ${st.model}</span>
        `;
        stepList.appendChild(item);
        return item;
    });

    let currentStep = 0;
    stageElements[0].classList.add('active');
    document.getElementById('step-icon-0').innerHTML = '<div class="spinner"></div>';

    const stageInterval = setInterval(() => {
        if (currentStep < stages.length - 1) {
            stageElements[currentStep].classList.remove('active');
            stageElements[currentStep].classList.add('completed');
            document.getElementById(`step-icon-${currentStep}`).textContent = '✓';

            currentStep++;
            stageElements[currentStep].classList.add('active');
            document.getElementById(`step-icon-${currentStep}`).innerHTML = '<div class="spinner"></div>';
        }
    }, 1800);

    try {
        const res = await fetch('/api/query', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', ...await getAuthHeaders()},
            body: JSON.stringify({query, provider, model, agent_models})
        });
        const responseText = await res.text();
        let data;
        try {
            data = JSON.parse(responseText);
        } catch (error) {
            const detail = responseText.trim() || `Empty response (HTTP ${res.status})`;
            throw new Error(`Server returned an invalid JSON response: ${detail}`);
        }

        clearInterval(stageInterval);
        stages.forEach((_, idx) => {
            const el = document.getElementById(`step-item-${idx}`);
            if (el) {
                el.classList.remove('active');
                el.classList.add('completed');
            }
            const ic = document.getElementById(`step-icon-${idx}`);
            if (ic) ic.textContent = '✓';
        });

        progressBox.classList.remove('active');
        resultsBox.classList.add('active');
        runBtn.disabled = false;
        const finalOutput = data.final_output || '';

        updateScoreMetric(data.final_score);
        updateResultTabs(data.final_score !== null && data.final_score !== undefined);
        document.getElementById('revVal').textContent = data.revision_count || 0;
        document.getElementById('timeVal').textContent = (data.elapsed_seconds || 1.4).toFixed(1) + 's';
        document.getElementById('modelBadge').textContent = model.split('/').pop();

        document.getElementById('tab-final').textContent = finalOutput;
        document.getElementById('tab-plan').textContent = data.plan || '';
        document.getElementById('tab-research').textContent = data.research || '';
        document.getElementById('tab-draft').textContent = data.draft || '';
        document.getElementById('tab-critique').textContent = data.critique || '';
        updateDownloadButtonState(finalOutput);

        await loadUserHistory();

    } catch(err) {
        clearInterval(stageInterval);
        alert('Error: ' + err);
        progressBox.classList.remove('active');
        runBtn.disabled = false;
    }
}

</script>
</body>
</html>
"""


class ThinkTankHandler(http.server.SimpleHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _require_firebase_user(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            self._send_json(401, {"error": "Sign in to use ThinkTank."})
            return False

        try:
            user = verify_firebase_id_token(authorization.removeprefix("Bearer "))
            return user
        except ValueError as error:
            self._send_json(401, {"error": str(error)})
        except RuntimeError as error:
            self._send_json(503, {"error": str(error)})
        return False

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif self.path == "/api/firebase-config":
            firebase_config = {
                "apiKey": Config.FIREBASE_API_KEY,
                "authDomain": Config.FIREBASE_AUTH_DOMAIN,
                "projectId": Config.FIREBASE_PROJECT_ID,
                "appId": Config.FIREBASE_APP_ID,
            }
            configured = all(firebase_config.values())
            response_data = {
                "configured": configured,
                "firebase_config": firebase_config if configured else None,
                "error": None if configured else "Firebase web configuration is missing on the server.",
            }
            self._send_json(200 if configured else 503, response_data)
        elif self.path.startswith("/api/models?"):
            if not self._require_firebase_user():
                return
            provider = urllib.parse.parse_qs(
                urllib.parse.urlsplit(self.path).query
            ).get("provider", [""])[0]
            if provider not in {"google-gemini", "nvidia-nim", "omniroute", "meta-model-api"}:
                response_data = {"error": "Unsupported provider"}
                status = 400
            else:
                try:
                    thinktank = ThinkTank(provider=provider)
                    response_data = {
                        "models": thinktank.list_available_models(provider),
                        "default_model": thinktank.model,
                    }
                    status = 200
                except Exception as error:
                    response_data = {"error": str(error)}
                    status = 502

            self._send_json(status, response_data)
        elif self.path.startswith("/api/history"):
            firebase_user = self._require_firebase_user()
            if not firebase_user:
                return
            try:
                parsed = urllib.parse.urlsplit(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                limit = int(params.get("limit", ["10"])[0])
                limit = max(1, min(limit, 25))
                history = fetch_user_query_history(firebase_user.get("uid"), limit=limit)
                self._send_json(200, {"history": history})
            except Exception as error:
                self._send_json(500, {"error": str(error)})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/query":
            firebase_user = self._require_firebase_user()
            if not firebase_user:
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body)

                query = payload.get("query", "")
                provider = payload.get("provider", "")
                model = payload.get("model", "nvidia/nemotron-3.5-lightning-30b-a3b")
                agent_models = payload.get("agent_models") or {}

                # Initialize ThinkTank using .env API keys
                tt = ThinkTank(provider=provider, model_name=model, agent_models=agent_models)
                pipeline_result = tt.process_query(query)

                # Build response data using the PipelineResult
                response_data = {
                    "query": pipeline_result.query,
                    "plan": str(pipeline_result.plan) if pipeline_result.plan is not None else None,
                    "research": str(pipeline_result.research) if pipeline_result.research is not None else None,
                    "draft": str(pipeline_result.draft) if pipeline_result.draft is not None else None,
                    "critique": str(pipeline_result.critique) if pipeline_result.critique is not None else None,
                    "final_score": pipeline_result.final_score,
                    "revision_count": pipeline_result.revision_count,
                    "final_output": str(pipeline_result.final_output) if pipeline_result.final_output is not None else None,
                    "elapsed_seconds": pipeline_result.elapsed_seconds,
                    "success": pipeline_result.success,
                }
                query_record = save_query_result_to_firestore(
                    user_uid=firebase_user.get("uid"),
                    query=query,
                    provider=provider,
                    model=model,
                    result_payload=response_data,
                )
                response_data["query_id"] = query_record["query_id"]
                response_data["result_id"] = query_record["result_id"]

            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
                # API key validation error
                response_data = {
                    "success": False,
                    "error": f"Invalid request or configuration: {str(e)}",
                    "final_output": f"⚠️ Request Error\n\n{str(e)}",
                    "final_score": 0,
                    "revision_count": 0,
                    "elapsed_seconds": 0,
                    "query_id": str(uuid.uuid4()),
                    "result_id": str(uuid.uuid4()),
                }
            except Exception as e:
                # Other errors
                response_data = {
                    "success": False,
                    "error": f"Pipeline Error: {str(e)}",
                    "final_output": f"⚠️ Processing Error\n\n{str(e)}\n\nPlease check your API key and try again.",
                    "final_score": 0,
                    "revision_count": 0,
                    "elapsed_seconds": 0,
                    "query_id": str(uuid.uuid4()),
                    "result_id": str(uuid.uuid4()),
                }

            self._send_json(200, response_data)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


class ThinkTankHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def run_server():
    # Fix Windows console encoding
    import sys
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

    server_address = ("", PORT)
    with ThinkTankHTTPServer(server_address, ThinkTankHandler) as httpd:
        print(f"🚀 ThinkTank Web Interface running at: http://localhost:{PORT}")
        print("🔑 API Key Management: All providers (Google Gemini, NVIDIA NIM) require valid API keys")
        print("📊 Status: Ready for secure API key validation and management")
        print("🔧 Commands available via CLI key manager")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
