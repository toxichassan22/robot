import os
from dotenv import load_dotenv

# Load .env variables into environment
load_dotenv()

# We can add validation logic here if needed, 
# but for now load_dotenv() is sufficient to populate os.environ 
# so that models.py and ears_mouth.py can read the API keys.
