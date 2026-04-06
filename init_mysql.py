import os
import pymysql
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
db_url = os.environ.get('DATABASE_URL')

if db_url and db_url.startswith('mysql'):
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip('/')
    
    try:
        # Connect to MySQL engine itself without specifying a database
        conn = pymysql.connect(
            host=parsed.hostname or 'localhost', 
            user=parsed.username or 'root', 
            password=parsed.password or ''
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        print(f"Successfully verified or created the MySQL Database '{db_name}'!")
    except Exception as e:
        print(f"Could not prepare database automatically: {e}")
else:
    print("No MySQL URL detected in .env.")
