from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

key = os.getenv("GROQ_API_KEY")

if key:
    print("Groq API key is configured.")
else:
    print("Groq API key is not configured. Add GROQ_API_KEY to the project-root .env file.")