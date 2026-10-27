import os
import sys
# Add the parent directory to sys.path to allow importing from adk_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from google.adk import Agent
from google.genai import types
from google.adk.tools import google_search  # The Google Search tool
from google.adk.models import Gemini, LlmResponse
from google.adk.apps.app import App

from adk_utils.plugins import LabExUtils

load_dotenv()

# Retry options help avoid the occasional error from popular models
# receiving too many requests at once.
RETRY_OPTIONS = types.HttpRetryOptions(initial_delay=1, max_delay=3, attempts=30)
plugins = [LabExUtils()]

root_agent = Agent(
    # name: A unique name for the agent.
    name="google_search_agent",
    # description: A short description of the agent's purpose, so
    # other agents in a multi-agent system know when to call it.
    description="Answer questions using Google Search.",
    # model: The LLM model that the agent will use:
    model=Gemini(model=os.getenv("MODEL"), retry_options=RETRY_OPTIONS),
    # instruction: Instructions (or the prompt) for the agent.
    instruction="You are an expert researcher. You stick to the facts.",
    # tools: functions to enhance the model's capabilities.
    # Add the google_search tool below.
    tools=[google_search]
)

app = App(
    name="my_google_search_agent",
    root_agent=root_agent,
    plugins=plugins
)


