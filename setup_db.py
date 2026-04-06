import pymysql
import os

try:
    # Attempt connecting with blank password (common for dev local setups like XAMPP)
    connection = pymysql.connect(host='localhost', user='root', password='')
    cursor = connection.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS job_portal")
    print("Database `job_portal` created successfully or already exists.")
except Exception as e:
    print(f"Failed to create database automatically: {e}")
    print("Please manually create a database named 'job_portal' in your MySQL server.")
