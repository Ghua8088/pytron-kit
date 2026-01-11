import argparse
import keyring
import time
import webbrowser
import requests
from ..console import log

SERVICE_NAME = "pytron-kit"
ACCOUNT_NAME = "github-token"
# NOTE: Replace this with the actual Client ID from your GitHub OAuth App
CLIENT_ID = "Ov23linvJ7QhMWN2tOth" 

def cmd_login(args: argparse.Namespace) -> int:
    log("GitHub Device Login", style="info")
    
    # 1. Ask GitHub for a "Device Code"
    try:
        response = requests.post(
            "https://github.com/login/device/code",
            headers={"Accept": "application/json"},
            data={"client_id": CLIENT_ID, "scope": "read:user"},
            timeout=10
        )
        data = response.json()
        
        if "error" in data:
            log(f"GitHub Error: {data.get('error_description', data['error'])}", style="error")
            log("Make sure the Client ID is correct and Device Flow is enabled in GitHub settings.", style="info")
            return 1

        device_code = data["device_code"]
        user_code = data["user_code"]       # e.g., "WDJB-VJTW"
        verification_uri = data["verification_uri"] # github.com/login/device
        interval = data["interval"]         # How often to check

        # 2. Show the user what to do
        log(f"1. Copy your one-time code: [bold green]{user_code}[/bold green]")
        log(f"2. Visit: {verification_uri}")
        
        print("")
        input("Press Enter to open the browser and authorize...")
        webbrowser.open(verification_uri)

        log("Waiting for authorization...", style="info")

        # 3. Poll GitHub until the user clicks "Approve"
        while True:
            time.sleep(interval)
            
            check_resp = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": CLIENT_ID, 
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                timeout=10
            )
            token_data = check_resp.json()

            if "access_token" in token_data:
                token = token_data["access_token"]
                
                # Success! Let's get the username for the welcome message
                user_res = requests.get(
                    "https://api.github.com/user", 
                    headers={"Authorization": f"token {token}"},
                    timeout=5
                )
                username = user_res.json().get("login", "User") if user_res.status_code == 200 else "User"
                
                keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, token)
                log(f"Successfully logged in as @{username}!", style="success")
                return 0
                
            if "error" in token_data:
                error = token_data["error"]
                if error == "authorization_pending":
                    continue # Keep polling
                elif error == "slow_down":
                    interval += 5 # GitHub is telling us to chill
                elif error == "expired_token":
                    log("Code expired. Please run 'pytron login' again.", style="error")
                    return 1
                else:
                    log(f"Authorization failed: {error}", style="error")
                    return 1
    except Exception as e:
        log(f"Login failed: {e}", style="error")
        return 1

def cmd_logout(args: argparse.Namespace) -> int:
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        log("Logged out. GitHub token removed from keyring.", style="success")
        return 0
    except keyring.errors.PasswordDeleteError:
        log("Already logged out.", style="warning")
        return 0
    except Exception as e:
        log(f"Logout failed: {e}", style="error")
        return 1

def get_github_token() -> str | None:
    import os
    # Priority 1: Environment Variable (highest priority/override)
    env_token = os.environ.get("PYTRON_GITHUB_TOKEN")
    if env_token:
        return env_token
        
    # Priority 2: Keyring
    try:
        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except Exception:
        return None
