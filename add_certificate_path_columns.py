import sqlite3

db_path = "website/database.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE doctor ADD COLUMN certificate_path VARCHAR(255);")
    print("doctor.certificate_path column added successfully.")
except sqlite3.OperationalError as e:
    print("Error or column already exists (doctor):", e)

try:
    cur.execute("ALTER TABLE pharmacist ADD COLUMN certificate_path VARCHAR(255);")
    print("pharmacist.certificate_path column added successfully.")
except sqlite3.OperationalError as e:
    print("Error or column already exists (pharmacist):", e)

conn.commit()
conn.close() 