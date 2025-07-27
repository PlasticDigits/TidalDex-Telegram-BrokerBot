"""
FastAPI server module for health checks and API endpoints.
"""
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn
import secrets
import time
from urllib.parse import urlencode

from utils.config import API_HOST, API_PORT, X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI, X_SCOPES
from requests_oauth2client import OAuth2Client, OAuth2AuthorizationCodeAuth
from db.utils import hash_user_id

# Configure logging
logger = logging.getLogger(__name__)

# Global storage for OAuth states (in production, use Redis or database)
oauth_states: Dict[str, Dict[str, Any]] = {}

# Create FastAPI app instance
app = FastAPI(
    title="TidalDex Telegram Bot API",
    description="API server for TidalDex Telegram Bot health checks and endpoints",
    version="1.0.0"
)

@app.get("/isup")
async def health_check() -> JSONResponse:
    """
    Health check endpoint to verify the service is running.
    
    Returns:
        JSONResponse: Status indicating the service is up
    """
    logger.info("Health check endpoint accessed")
    return JSONResponse(
        content={"isUp": True},
        status_code=200
    )

@app.get("/")
async def root() -> JSONResponse:
    """
    Root endpoint with basic service information.
    
    Returns:
        JSONResponse: Basic service information
    """
    return JSONResponse(
        content={
            "service": "TidalDex Telegram Bot API",
            "status": "running",
            "endpoints": ["/isup", "/"]
        },
        status_code=200
    )

@app.get("/x-oauth")
async def x_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None)
) -> HTMLResponse:
    """
    OAuth 2.0 callback endpoint for X (Twitter) authentication.
    
    Args:
        code: Authorization code from X
        state: State parameter to prevent CSRF attacks
        error: Error code if authentication failed
        error_description: Human-readable error description
        
    Returns:
        HTMLResponse: Success or error page
    """
    logger.info(f"OAuth callback received - state: {state}, code present: {bool(code)}, error: {error}")
    
    try:
        # Handle OAuth errors
        if error:
            error_msg = f"OAuth authentication failed: {error}"
            if error_description:
                error_msg += f" - {error_description}"
            logger.error(error_msg)
            
            return HTMLResponse(
                content=f"""
                <html>
                    <head><title>X Authentication Failed</title></head>
                    <body>
                        <h1>Authentication Failed</h1>
                        <p>{error_msg}</p>
                        <p>Please try again by returning to your Telegram bot and using the /x command.</p>
                    </body>
                </html>
                """,
                status_code=400
            )
        
        # Validate state parameter
        if not state or state not in oauth_states:
            logger.error(f"Invalid or missing state parameter: {state}")
            return HTMLResponse(
                content="""
                <html>
                    <head><title>Invalid Request</title></head>
                    <body>
                        <h1>Invalid Request</h1>
                        <p>Invalid or expired authentication request. Please try again.</p>
                    </body>
                </html>
                """,
                status_code=400
            )
        
        # Validate authorization code
        if not code:
            logger.error("Missing authorization code")
            return HTMLResponse(
                content="""
                <html>
                    <head><title>Missing Authorization Code</title></head>
                    <body>
                        <h1>Authorization Failed</h1>
                        <p>No authorization code received. Please try again.</p>
                    </body>
                </html>
                """,
                status_code=400
            )
        
        # Retrieve state data
        state_data = oauth_states.get(state)
        if not state_data:
            logger.error(f"State data not found for state: {state}")
            return HTMLResponse(
                content="""
                <html>
                    <head><title>Session Expired</title></head>
                    <body>
                        <h1>Session Expired</h1>
                        <p>Your authentication session has expired. Please try again.</p>
                    </body>
                </html>
                """,
                status_code=400
            )
        
        # Check state expiration (5 minutes)
        if time.time() - state_data.get('created_at', 0) > 300:
            logger.error(f"Expired state: {state}")
            oauth_states.pop(state, None)
            return HTMLResponse(
                content="""
                <html>
                    <head><title>Session Expired</title></head>
                    <body>
                        <h1>Session Expired</h1>
                        <p>Your authentication session has expired. Please try again.</p>
                    </body>
                </html>
                """,
                status_code=400
            )
        
        # Store the authorization code and mark as completed
        state_data['authorization_code'] = code
        state_data['completed_at'] = time.time()
        state_data['status'] = 'completed'
        
        logger.info(f"OAuth callback completed successfully for state: {state}")
        
        return HTMLResponse(
            content="""
            <html>
                <head><title>X Authentication Successful</title></head>
                <body>
                    <h1>✅ Authentication Successful!</h1>
                    <p>Your X account has been successfully connected to the TidalDex Bot.</p>
                    <p>You can now close this window and return to Telegram to complete the process.</p>
                    <script>
                        // Auto-close after 3 seconds
                        setTimeout(function() {
                            window.close();
                        }, 3000);
                    </script>
                </body>
            </html>
            """,
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        return HTMLResponse(
            content="""
            <html>
                <head><title>Server Error</title></head>
                <body>
                    <h1>Server Error</h1>
                    <p>An error occurred while processing your request. Please try again.</p>
                </body>
            </html>
            """,
            status_code=500
        )

def create_oauth_state(user_id: int, telegram_chat_id: int, pin: Optional[str] = None) -> str:
    """
    Create a new OAuth state for a user.
    
    Args:
        user_id: Telegram user ID
        telegram_chat_id: Telegram chat ID
        pin: User's PIN for encryption (optional)
        
    Returns:
        Generated state string
    """
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {
        'user_id': user_id,
        'telegram_chat_id': telegram_chat_id,
        'pin': pin,
        'created_at': time.time(),
        'status': 'pending'
    }
    
    # Clean up old states (older than 10 minutes)
    current_time = time.time()
    expired_states = [
        s for s, data in oauth_states.items() 
        if current_time - data.get('created_at', 0) > 600
    ]
    for expired_state in expired_states:
        oauth_states.pop(expired_state, None)
    
    logger.info(f"Created OAuth state {state} for user {hash_user_id(user_id)}")
    return state

def get_oauth_state_data(state: str) -> Optional[Dict[str, Any]]:
    """
    Get OAuth state data.
    
    Args:
        state: State string
        
    Returns:
        State data or None if not found
    """
    return oauth_states.get(state)

def cleanup_oauth_state(state: str) -> None:
    """
    Clean up OAuth state after use.
    
    Args:
        state: State string to remove
    """
    oauth_states.pop(state, None)
    logger.info(f"Cleaned up OAuth state: {state}")

async def start_api_server() -> None:
    """
    Start the FastAPI server.
    
    This function runs the FastAPI server with uvicorn.
    """
    logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
    
    config = uvicorn.Config(
        app=app,
        host=API_HOST,
        port=API_PORT,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    await server.serve()

def run_api_server() -> None:
    """
    Synchronous wrapper to run the API server.
    
    This is used when running the API server in a separate thread.
    """
    import asyncio
    
    try:
        asyncio.run(start_api_server())
    except Exception as e:
        logger.error(f"Error starting API server: {e}")
        raise 