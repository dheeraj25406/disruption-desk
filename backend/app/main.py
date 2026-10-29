import logging,uuid
from fastapi import FastAPI,Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.db import Base,engine
from app.seed import seed
from app.core.config import settings
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger=logging.getLogger("flyo")
app=FastAPI(title="Flyo Disruption Desk API",version="2.0.0",description="Synthetic airline disruption recovery demo. No live airline data or booking actions.")
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(","),allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
@app.middleware("http")
async def request_id(request:Request,call_next):
    rid=request.headers.get("X-Request-ID") or str(uuid.uuid4());response=await call_next(request);response.headers["X-Request-ID"]=rid;logger.info("request_id=%s method=%s path=%s status=%s",rid,request.method,request.url.path,response.status_code);return response
@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    seed()

app.include_router(router)
