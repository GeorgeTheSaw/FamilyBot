from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION_NAME

# Подключение к MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
tasks_collection = db[MONGO_COLLECTION_NAME]