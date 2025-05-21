import sqlite3

def update_database():
    # Connect to the database
    conn = sqlite3.connect('website/database.db')
    cursor = conn.cursor()
    
    try:
        # Add new columns to doctor table
        cursor.execute('ALTER TABLE doctor ADD COLUMN clinic_address VARCHAR(255)')
        cursor.execute('ALTER TABLE doctor ADD COLUMN certification TEXT')
        cursor.execute('ALTER TABLE doctor ADD COLUMN phone_number VARCHAR(50)')
        
        # Commit the changes
        conn.commit()
        print("Successfully added new columns to doctor table")
        
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        print("Some columns may already exist")
    
    finally:
        # Close the connection
        conn.close()

if __name__ == '__main__':
    update_database() 