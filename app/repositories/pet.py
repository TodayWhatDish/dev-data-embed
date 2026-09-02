from app.core.db import fetch

def get_breeds():
    return fetch("SELECT * FROM breed")
