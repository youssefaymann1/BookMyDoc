import sqlite3

db_path = "website/database.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE user ADD COLUMN id_photo_path VARCHAR(255);")
    print("id_photo_path column added successfully.")
except sqlite3.OperationalError as e:
    print("Error or column already exists:", e)

conn.commit()
conn.close() 