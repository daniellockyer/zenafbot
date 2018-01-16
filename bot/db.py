import psycopg2
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

def get_or_create_user(user):
    cursor = get_connection().cursor()
    
    cursor.execute('SELECT * FROM users WHERE id = %s', (user.id,))
    result = cursor.fetchone()
    
    if result is None:
        values = []
        for attribute in ['id', 'first_name', 'last_name', 'username']:
            value = getattr(user, attribute, None)
            values.append(value)
        
        cursor.execute("INSERT INTO users(id, first_name, last_name, username) VALUES (%s, %s, %s, %s)", values)
        
        cursor.execute('SELECT * FROM users WHERE id = %s', (user.id,))
        result = cursor.fetchone()

    get_connection().commit()
    cursor.close()

    return result

def increase_streak_of(id):
    cursor = get_connection().cursor()
    cursor.execute('UPDATE users SET streak = streak + 1 WHERE id = %s', (id,))
    get_connection().commit()

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