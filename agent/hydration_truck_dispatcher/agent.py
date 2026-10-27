import os
from dotenv import load_dotenv

from google.adk import Agent
from google.genai import types
from google.adk.tools import google_search

load_dotenv()

# Retry options help avoid the occasional error from popular models
# receiving too many requests at once.
RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)

root_agent = Agent(
    name="google_search_agent",
    description="Answer questions using Google Search.",
    model=os.getenv("MODEL", "gemini-3.8-flash"),
    instruction="You are an expert researcher. You stick to the facts.",
    tools=[google_search],
)





