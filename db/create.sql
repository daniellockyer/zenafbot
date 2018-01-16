CREATE DATABASE zenirl;

CREATE TABLE users(
    id INTEGER UNIQUE NOT NULL,
    first_name text NOT NULL,
    last_name text,
    username text,
    streak INTEGER NOT NULL DEFAULT 0
);