# Last Updated: 2026-08-12
import csv
import sqlite3

con = sqlite3.connect('user.db')
cur = con.cursor()

cur.execute('DROP TABLE IF EXISTS pet_customers')
cur.execute('''
CREATE TABLE pet_customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT,
    phone TEXT,
    email TEXT,
    city TEXT,
    account_type TEXT,
    joined_at TEXT
)
''')

cur.execute('DROP TABLE IF EXISTS pet_profiles')
cur.execute('''
CREATE TABLE pet_profiles (
    pet_id TEXT PRIMARY KEY,
    customer_id TEXT,
    breed TEXT,
    age INTEGER,
    gender TEXT,
    weight_kg REAL,
    body_type TEXT,
    neutered INTEGER,
    allergies TEXT,
    feeding_purpose TEXT,
    diet_preference TEXT,
    food_form_preference TEXT,
    budget INTEGER,
    place_type_preference TEXT,
    updated_at TEXT
)
''')

cur.execute('DROP TABLE IF EXISTS pet_products')
cur.execute('''
CREATE TABLE pet_products (
    product_id TEXT PRIMARY KEY,
    category TEXT,
    sub_category TEXT,
    brand TEXT,
    product_name TEXT,
    price INTEGER,
    weight_g INTEGER,
    target_feeding_purpose TEXT,
    target_food_form TEXT,
    ingredients TEXT,
    concerns TEXT,
    tags TEXT,
    description TEXT
)
''')

cur.execute('DROP TABLE IF EXISTS pet_purchases')
cur.execute('''
CREATE TABLE pet_purchases (
    purchase_id TEXT PRIMARY KEY,
    customer_id TEXT,
    pet_id TEXT,
    product_id TEXT,
    category TEXT,
    purchased_at TEXT,
    quantity INTEGER,
    rating INTEGER,
    review TEXT,
    is_holdout INTEGER
)
''')


def load_csv(table, path):
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0])
    marks = ','.join(['?'] * len(cols))
    values = [tuple(row[c] for c in cols) for row in rows]
    cur.executemany(f'INSERT INTO "{table}" VALUES ({marks})', values)
    print(f'{table}: {len(rows)} rows')


load_csv('pet_customers', 'data/pet_customers.csv')
load_csv('pet_profiles', 'data/pet_profiles.csv')
load_csv('pet_products', 'data/pet_products.csv')
load_csv('pet_purchases', 'data/pet_purchases.csv')

con.commit()
con.close()
