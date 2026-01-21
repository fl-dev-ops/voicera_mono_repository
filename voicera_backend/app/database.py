"""
Database connection and utilities for MongoDB.
"""
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    """MongoDB connection manager."""
    
    client: MongoClient = None
    database: Database = None

mongodb = MongoDB()

def connect_to_mongo():
    """Create database connection."""
    try:
        mongodb.client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=5000
        )
        # Test the connection
        mongodb.client.admin.command('ping')
        mongodb.database = mongodb.client[settings.MONGODB_DATABASE]
        logger.info("Connected to MongoDB successfully")
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

def close_mongo_connection():
    """Close database connection."""
    if mongodb.client:
        mongodb.client.close()
        logger.info("Disconnected from MongoDB")

def get_database() -> Database:
    """Get database instance."""
    if mongodb.database is None:
        connect_to_mongo()
    return mongodb.database

