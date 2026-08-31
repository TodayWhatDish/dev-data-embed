from app.core.db import dicts

def get_breeds():
    return dicts("SELECT * FROM breed")
