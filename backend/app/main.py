from fastapi import FastAPI
from routes.repurpose import router as repurpose_router

app = FastAPI()

app.include_router(repurpose_router, prefix="/repurpose")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)