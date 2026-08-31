from app.core.db import query, dicts

def get_col_names(table_name):
    return query(f'SELECT name FROM pragma_table_info(\'{table_name}\');')

def get_allgens():
    return dicts("""
    SELECT *
    FROM allergen
    ORDER BY allergen_id, parent_id;
""")

def get_animal_categories():
    return dicts("SELECT * FROM animal_category")

def get_breeds():
    return dicts("SELECT * FROM breed")
