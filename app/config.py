import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")  # Gemini API key only
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "mock-project-id")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-east1")

# Initialize global Vertex AI config with mock values to bypass GCP auth checks
from google.cloud import aiplatform
aiplatform.init(project="mock-project-id", location="us-east1")

@dataclass
class AgentConfig:
    # Reads model from environment GEMINI_MODEL. Default gemini-2.5-flash (the 1.5 family is retired and returns 404). Use gemini-2.5-flash-lite for tighter free-tier quota.
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    mcp_server_port: int = 8090
    max_iterations: int = 3
    pii_redaction_enabled: bool = True
    injection_detection_enabled: bool = True

config = AgentConfig()
