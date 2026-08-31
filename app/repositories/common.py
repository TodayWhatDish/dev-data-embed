from app.core.db import query, dicts

def get_col_names(table_name):
    return query(f'SELECT name FROM pragma_table_info(\'{table_name}\');')
