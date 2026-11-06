import os
import hmac
import hashlib
import json
import requests

from dotenv import load_dotenv

load_dotenv()

secret = os.getenv("GITHUB_WEBHOOK_SECRET")

payload = {
    "action": "opened",
    "number": 101,
    "repository": {
        "full_name": "tme-demo-developer/tme-config-demo"
    },
    "pull_request": {
        "number": 101,
        "title": "Test webhook integration",
        "state": "open"
    }
}

body = json.dumps(payload).encode("utf-8")

signature = "sha256=" + hmac.new(
    secret.encode("utf-8"),
    body,
    hashlib.sha256
).hexdigest()

response = requests.post(
    "http://127.0.0.1:5000/webhook",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": signature
    }
)

print("HTTP Status:", response.status_code)
print("Response:", response.json())