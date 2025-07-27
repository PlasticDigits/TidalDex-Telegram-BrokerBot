"""
FastAPI server module for health checks and API endpoints.
"""
import logging
from typing import Dict, Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from utils.config import API_HOST, API_PORT

# Configure logging
logger = logging.getLogger(__name__)

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