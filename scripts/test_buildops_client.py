import json
from pathlib import Path
from dotenv import load_dotenv
from app.buildops_client import BuildOpsClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

bo = BuildOpsClient()

prop = bo.get_property_by_id("a2b57023-e888-44a7-ab42-dd26107fa1cb")

print(json.dumps(prop, indent=2))