"""Phase 1: PyMongo database connection and dependency provider for MongoDB."""
import logging
from pymongo import MongoClient
from pymongo.database import Database
from app.core.config import settings

logger = logging.getLogger("ai_interviewer")

# Initialize global MongoClient instance
client: MongoClient = MongoClient(
    settings.MONGODB_URL,
    serverSelectionTimeoutMS=5000
)
database: Database = client[settings.DATABASE_NAME]

def get_db() -> Database:
    """FastAPI database dependency returning the active PyMongo Database instance."""
    return client[settings.DATABASE_NAME]
