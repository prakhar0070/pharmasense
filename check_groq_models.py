import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

models = client.models.list()
print("Models available to your key:")
for m in models.data:
    print(" -", m.id)
