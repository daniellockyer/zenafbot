import psycopg2
from psycopg2.sql import Identifier, SQL
import os

CONNECTION = None
DB_NAME = os.environ.get('DB_NAME', 'zenirlbot')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')
DB_HOST = os.environ.get('DB_HOST', 'localhost')

def get_connection():
    global CONNECTION

    if not CONNECTION or CONNECTION.closed != 0:
        CONNECTION = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port="5432"
        )

    return CONNECTION

def set_has_pmed(id):
    cursor = get_connection().cursor()
    cursor.execute('UPDATE users SET haspm = TRUE WHERE id = %s', (id,))
    get_connection().commit()
    cursor.close()

def increase_streak_of(id):
    cursor = get_connection().cursor()
    cursor.execute('UPDATE users SET streak = streak + 1 WHERE id = %s', (id,))
    get_connection().commit()
    cursor.close()

def get_streak_of(id):
    cursor = get_connection().cursor()
    cursor.execute('SELECT streak FROM users WHERE id = %s', (id,))
    result = cursor.fetchone()
    get_connection().commit()
    return result[0]

def get_top(n):
    cursor = get_connection().cursor()
    cursor.execute(
        'SELECT first_name, last_name, username, streak FROM users ORDER BY streak DESC LIMIT %s',
        (n,)
    )
    results = cursor.fetchall()
    get_connection().commit()
    return results

def add_to_table(table, id, value):
    cursor = get_connection().cursor()
    cursor.execute(SQL("INSERT INTO {} (id, value) VALUES (%s, %s)".format(Identifier(table))), (id, value))
    get_connection().commit()
    cursor.close()

def get_values(table, start_date=None, end_date=None, user_id=None):
    cursor = get_connection().cursor()
    query = SQL("SELECT value, created_at FROM {} WHERE "\
                    "(%s is NULL OR id = %s) "\
                "AND (%s is NULL OR created_at > %s) "\
                "AND (%s is NULL OR created_at < %s);".format(Identifier(table)))
    cursor.execute(query, (user_id, user_id, start_date, start_date, end_date, end_date))
    results = cursor.fetchall()
    get_connection().commit()
    return results