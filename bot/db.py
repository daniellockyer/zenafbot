import os
import psycopg2
from psycopg2 import sql

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

def set_has_pmed(user_id):
    cursor = get_connection().cursor()
    cursor.execute('UPDATE users SET haspm = TRUE WHERE id = %s', (user_id,))
    get_connection().commit()
    cursor.close()

def get_streak_of(user_id):
    cursor = get_connection().cursor()
    cursor.execute(
        sql.SQL(
            "WITH t AS ("\
                "SELECT distinct(meditation.created_at::date) as created_at "\
                "FROM meditation "\
                "WHERE id = %s"\
            ")"\
            "SELECT count(*) FROM t WHERE t.created_at > ("\
                "SELECT d.d "\
                "from generate_series('2018-01-01'::date, TIMESTAMP 'yesterday'::date, '1 day') d(d) "\
                "left outer join t on t.created_at = d.d::date "\
                "where t.created_at is null "\
                "order by d.d desc "\
                "limit 1"\
            ")"
        ), (user_id,)
    )
    results = cursor.fetchall()
    get_connection().commit()
    return results[0]

#Not sure that a single nice SQL expression is possible for this now
def get_top(count):
    results = []
    cursor = get_connection().cursor()
    cursor.execute("SELECT * FROM users;")
    users = cursor.fetchall()
    get_connection().commit()
    for user in users:
        streak = get_streak_of(user[0])
        results.append((user[1], user[2], user[3], streak))
    results.sort(key=lambda x: x[3], reverse=True)
    return results[:count]

def add_to_table(table, user_id, value, backdate=None):
    cursor = get_connection().cursor()
    if backdate:
        cursor.execute(sql.SQL("INSERT INTO {} (id, value, created_at) VALUES (%s, %s, %s)").format(sql.Identifier(table)), (user_id, value, backdate))
    else:
        cursor.execute(sql.SQL("INSERT INTO {} (id, value) VALUES (%s, %s)").format(sql.Identifier(table)), (user_id, value))
    get_connection().commit()
    cursor.close()

def add_meditation_reminder(user_id, value, midnight):
    cursor = get_connection().cursor()
    cursor.execute("INSERT INTO meditationreminders (id, value, midnight) VALUES (%s, %s, %s)", (user_id, value, midnight))
    get_connection().commit()
    cursor.close()

def get_values(table, start_date=None, end_date=None, user_id=None, value=None):
    cursor = get_connection().cursor()
    query = sql.SQL("SELECT * FROM {} WHERE "\
                    "(%s is NULL OR id = %s) "\
                    "AND (%s is NULL OR created_at > %s) "\
                    "AND (%s is NULL OR created_at < %s) "\
                    "AND (%s is NULL OR value = %s);").format(sql.Identifier(table))
    cursor.execute(query, (user_id, user_id, start_date, start_date, end_date, end_date, value, value))
    results = cursor.fetchall()
    get_connection().commit()
    return results
