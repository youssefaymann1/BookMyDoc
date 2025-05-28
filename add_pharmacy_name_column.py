from website import db
from website.models import Pharmacist
from sqlalchemy import inspect

def add_pharmacy_name_column():
    # Get the inspector
    inspector = inspect(db.engine)
    
    # Check if the column exists
    columns = [column['name'] for column in inspector.get_columns('pharmacist')]
    
    if 'pharmacy_name' not in columns:
        try:
            # Add the column using SQLAlchemy
            db.engine.execute('ALTER TABLE pharmacist ADD COLUMN pharmacy_name VARCHAR(255);')
            print("pharmacy_name column added successfully.")
        except Exception as e:
            print("Error adding column:", e)
    else:
        print("pharmacy_name column already exists.")

if __name__ == "__main__":
    add_pharmacy_name_column() 