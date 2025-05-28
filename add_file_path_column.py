import sqlite3

db_path = "website/database.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE medical_record ADD COLUMN file_path VARCHAR(255);")
    print("file_path column added successfully.")
except sqlite3.OperationalError as e:
    print("Error or column already exists:", e)

conn.commit()
conn.close() 