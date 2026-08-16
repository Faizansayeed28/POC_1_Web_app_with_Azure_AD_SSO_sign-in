import os, requests, jwt
from flask import Flask, jsonify, request
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Load tenant and API client ID with fallback defaults to prevent None values
TENANT_ID     = os.getenv("AZURE_TENANT_ID", "7a2369dd-7d9f-421a-866f-c114c486150a")
API_CLIENT_ID = os.getenv("AZURE_API_CLIENT_ID", "911e5d00-729e-47d5-89b0-96f325dbb4c5")

# Public keys endpoint using dynamic TENANT_ID
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"

# Accept both v1.0 and v2.0 token issuers
VALID_ISSUERS = [
    f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
    f"https://sts.windows.net/{TENANT_ID}/"
]

# Accept both raw Client ID GUID and api:// App ID URI formats
VALID_AUDIENCES = [API_CLIENT_ID, f"api://{API_CLIENT_ID}"]

def _get_signing_keys():
    """Fetch Azure AD public keys for JWT signature verification."""
    resp = requests.get(JWKS_URI)
    return {k["kid"]: jwt.algorithms.RSAAlgorithm.from_jwk(k)
            for k in resp.json()["keys"]}

def require_auth(required_scope=None):
    """Decorator: validates bearer token and optionally checks scope."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify(error="Missing bearer token"), 401
            
            token = auth.split(" ", 1)[1]
            try:
                header = jwt.get_unverified_header(token)
                keys   = _get_signing_keys()
                key    = keys.get(header.get("kid"))

                if not key:
                    return jsonify(error="Invalid token header: Key ID (kid) not found"), 401

                claims = jwt.decode(
                    token, key,
                    algorithms=["RS256"],
                    issuer=VALID_ISSUERS,
                    audience=VALID_AUDIENCES,
                    options={"verify_exp": True}
                )
                
                # Check scope if required
                if required_scope:
                    scopes = claims.get("scp", "").split()
                    if required_scope not in scopes:
                        return jsonify(error="Insufficient scope"), 403

                request.token_claims = claims  # make claims available in route
            except jwt.ExpiredSignatureError:
                return jsonify(error="Token expired"), 401
            except Exception as e:
                return jsonify(error=f"Invalid token: {e}"), 401
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Protected endpoint — requires Data.Read scope
@app.route("/api/data")
@require_auth(required_scope="Data.Read")
def get_data():
    claims = request.token_claims
    user = (
        claims.get("preferred_username") 
        or claims.get("upn") 
        or claims.get("email") 
        or claims.get("sub", "unknown")
    )
    return jsonify(message=f"Hello {user}! Here is your protected data.",
                   items=["item_1", "item_2", "item_3"])

# Public endpoint — no auth needed
@app.route("/api/health")
def health():
    return jsonify(status="ok")

if __name__ == "__main__":
    app.run(port=6000, debug=True)