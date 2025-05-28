import sqlite3

db_path = "website/database.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE user ADD COLUMN photo_path VARCHAR(255);")
    print("photo_path column added successfully.")
except sqlite3.OperationalError as e:
    print("Error or column already exists:", e)

conn.commit()
conn.close() 