# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Import routers
from instagram import router as instagram_router
from poe_endpoints import router as poe_router
from openai_endpoints import router as openai_router

app = FastAPI()

# CORS Configuration
origins = ["*"]

expose_headers = [
    "Access-Control-Allow-Origin"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],    # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allow all headers
    expose_headers=expose_headers
)

# Health Check Endpoint
@app.get('/health')
def health():
    print('health endpoint')
    return "200"

# Root Endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse(content={"message": "Hello world!"}, status_code=200)

# Include Routers
app.include_router(instagram_router)
app.include_router(poe_router)
app.include_router(openai_router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)