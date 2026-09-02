from app.core.db import fetch

def get_allgens():
    return fetch("""
    SELECT *
    FROM allergen
    ORDER BY allergen_id, parent_id;
""")

def get_animal_categories():
    return fetch("SELECT * FROM animal_category")
