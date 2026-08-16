# POC 1 — Web App SSO with Azure AD (Entra ID)

> Sign users into a Flask web app using their Microsoft / Azure AD accounts via OpenID Connect (OIDC) authorization code flow.

---

## Overview

This POC demonstrates how to integrate **Azure Active Directory (Entra ID)** into a Python Flask web application so that users can sign in with their Microsoft work or school accounts — without managing any passwords yourself.

**Authentication flow:**

```
User clicks "Sign in"
  → Redirected to login.microsoftonline.com
  → User authenticates (Azure handles MFA, passwords, etc.)
  → Azure redirects back to /auth/callback with an auth code
  → App exchanges code for ID token + access token
  → User identity stored in session — user is logged in
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| Azure account | Free tier — [portal.azure.com](https://portal.azure.com) |
| Python | 3.8 or higher |
| pip packages | `flask`, `msal`, `python-dotenv` |

---

## Azure Portal Setup

### 1. Register the app

1. Go to **Microsoft Entra ID → App registrations → + New registration**
2. Fill in:
   - **Name:** `MyWebApp-POC1`
   - **Supported account types:** `Accounts in this organizational directory only (Single tenant)`
   - **Redirect URI (Web):** `http://localhost:5000/auth/callback`
3. Click **Register**
4. From the **Overview** page, copy:
   - `Application (client) ID` → your `CLIENT_ID`
   - `Directory (tenant) ID` → your `TENANT_ID`

### 2. Create a client secret

1. Go to **Certificates & secrets → + New client secret**
2. Description: `poc1-secret`, Expires: `6 months`
3. Click **Add**
4. **Copy the Value immediately** — it is only shown once

### 3. Verify authentication settings

Go to **Authentication** and confirm:

- Platform = **Web**
- Redirect URI = `http://localhost:5000/auth/callback`
- Logout URL = `http://localhost:5000/logout`
- **ID tokens** checkbox = ✅ checked

---

## Project Structure

```
poc1-azure-sso/
├── app.py          # Flask application
├── .env            # Credentials (never commit this)
├── .gitignore
└── requirements.txt
```

---

## Installation

```bash
# Clone or create the project folder
mkdir poc1-azure-sso && cd poc1-azure-sso

# Install dependencies
pip install flask msal python-dotenv
```

---

## Configuration

Create a `.env` file in the project root:

```env
# .env — never commit this file to git
AZURE_CLIENT_ID=your-application-client-id-here
AZURE_TENANT_ID=your-directory-tenant-id-here
AZURE_CLIENT_SECRET=your-client-secret-value-here
AZURE_REDIRECT_URI=http://localhost:5000/auth/callback
SECRET_KEY=any-random-string-for-flask-session
```

Create a `.gitignore`:

```
.env
__pycache__/
*.pyc
```

---

## Application Code

Create `app.py`:

```python
import os, msal
from flask import Flask, redirect, url_for, session, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

CLIENT_ID     = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID     = os.getenv("AZURE_TENANT_ID")
REDIRECT_URI  = os.getenv("AZURE_REDIRECT_URI")
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES        = ["User.Read"]  # MS Graph — read signed-in user profile


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
        return (
            f"<h2>Hello, {user['name']}!</h2>"
            f"<p>{user['preferred_username']}</p>"
            f"<a href='/logout'>Logout</a>"
        )
    return '<a href="/login">Sign in with Microsoft</a>'


# 2. Kick off login — redirect user to Azure AD
@app.route("/login")
def login():
    msal_app = _build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        state=os.urandom(16).hex()  # CSRF protection
    )
    return redirect(auth_url)


# 3. Azure AD sends the auth code here
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

    # Store user claims from the ID token in the session
    session["user"] = result.get("id_token_claims")
    return redirect(url_for("index"))


# 4. Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(
        AUTHORITY + "/oauth2/v2.0/logout"
        "?post_logout_redirect_uri=http://localhost:5000"
    )


if __name__ == "__main__":
    app.run(port=5000, debug=True)
```

---

## Running the App

```bash
python app.py
```

Open your browser at `http://localhost:5000`.

---

## Testing Checklist

| Step | Expected result |
|---|---|
| Open `http://localhost:5000` | See "Sign in with Microsoft" link |
| Click the link | Redirected to `login.microsoftonline.com` |
| Sign in with Azure AD credentials | Redirected back to `/auth/callback` |
| Callback processed | Page shows `Hello, [Your Name]!` with email |
| Click Logout | Session cleared, redirected to Azure logout |

---

## What's in the ID Token

After login, `session["user"]` contains these claims:

```json
{
  "name": "John Doe",
  "preferred_username": "john@yourcompany.com",
  "oid": "<unique user object ID in Azure AD>",
  "tid": "<your tenant ID>",
  "sub": "<subject — user identifier>",
  "exp": 1720000000,
  "roles": []
}
```

Use `oid` as a stable, unique user identifier in your database — it does not change even if the user's email address changes.

---

## Common Errors

| Error code | Cause | Fix |
|---|---|---|
| `AADSTS50011` | Redirect URI mismatch | The URI in your code must exactly match the portal registration (including trailing slash) |
| `AADSTS700016` | App not found | Double-check `CLIENT_ID` and `TENANT_ID` in your `.env` |
| `AADSTS7000218` | Client secret missing | Ensure `CLIENT_SECRET` is set and not expired |
| `400 No code received` | User cancelled login or session mismatch | Clear browser cookies and retry |

---

## How It Works

This app uses **MSAL (Microsoft Authentication Library)** for Python, which handles the full OAuth 2.0 / OIDC protocol:

1. `get_authorization_request_url()` builds the Azure AD login URL with the correct parameters (client ID, scopes, redirect URI, state for CSRF protection).
2. Azure authenticates the user and redirects back with a short-lived `code`.
3. `acquire_token_by_authorization_code()` exchanges that code (plus the client secret) for an **ID token** and **access token**. The client secret proves your server's identity to Azure — it never travels to the browser.
4. The ID token's claims (name, email, OID) are decoded and stored in the Flask session.

---

## Security Notes

- Never commit `.env` to version control
- Never log or expose `CLIENT_SECRET` or raw tokens
- The `state` parameter in the login URL prevents CSRF attacks
- For production, use a **certificate** instead of a client secret
- For production, use HTTPS — never serve tokens over plain HTTP
- Consider using `msal.SerializableTokenCache` for token caching and silent refresh

---

## References

- [MSAL Python docs](https://learn.microsoft.com/en-us/azure/active-directory/develop/msal-python-adfs-support)
- [Microsoft identity platform — web app sign-in quickstart](https://learn.microsoft.com/en-us/azure/active-directory/develop/web-app-quickstart)
- [OpenID Connect on the Microsoft identity platform](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-protocols-oidc)
