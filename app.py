import os, msal
from flask import Flask, jsonify, redirect, url_for, session, request
from dotenv import load_dotenv
import requests as http_requests

load_dotenv("webapp1.env")
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID     = os.getenv("AZURE_TENANT_ID")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")

required_env = ["SECRET_KEY", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_REDIRECT_URI"]
missing_env = [name for name in required_env if not os.getenv(name)]
if missing_env:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_env)}")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["api://911e5d00-729e-47d5-89b0-96f325dbb4c5/Data.Read"]  # MS Graph — read signed-in user profile

def _build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )

# 1. Home page
@app.route("/")
def index():
    user = session.get("user")
    if user:
        return f"<h2>Hello, {user['name']}!</h2><p>{user['preferred_username']}</p><a href='/logout'>Logout</a>"
    return '<a href="/login">Sign in with Microsoft</a>'

# 2. Kick off login — redirect user to Azure AD
@app.route("/login")
def login():
    msal_app = _build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        SCOPES, redirect_uri=REDIRECT_URI,
        state=os.urandom(16).hex()  # CSRF protection
    )
    return redirect(auth_url)

# 3. Azure AD sends auth code here
@app.route("/auth/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Login failed — no code received", 400
    msal_app = _build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    if "error" in result:
        return f"Error: {result['error_description']}", 400
        # --- ADD THESE LINES TO LOG YOUR DATA ---
    print("\n================ CONFIG CHECK ================")
    print("Python-side requested SCOPES:", SCOPES)
    print("Returned Access Token:")
    print(result.get("access_token"))
    print("==============================================\n")
    # ----------------------------------------
    # Store user claims from the ID token
    session["user"] = result.get("id_token_claims")
    session["access_token"]  = result["access_token"]  
    return redirect(url_for("index"))

# 4. Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        AUTHORITY + "/oauth2/v2.0/logout?post_logout_redirect_uri=http://localhost:5000"
    )

@app.route("/call-api")
def call_api():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("login"))

    resp = http_requests.get(
        "http://localhost:6000/api/data",
        headers={"Authorization": f"Bearer {token}"}
    )
    return jsonify(resp.json())

if __name__ == "__main__":
    app.run(port=5000, debug=True)