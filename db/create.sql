\connect zenirlbot

CREATE TABLE users(
    id INTEGER UNIQUE NOT NULL,
    first_name text NOT NULL,
    last_name text,
    username text,
    streak INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE timelog(
    id INTEGER NOT NULL REFERENCES users(id),
    minutes INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);