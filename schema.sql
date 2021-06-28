DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS head_song;
DROP TABLE IF EXISTS link_song;

CREATE TABLE user(
    id TEXT NOT NULL PRIMARY KEY
);

CREATE TABLE head_song(
    head_number INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    u_id TEXT NOT NULL,
    playlist TEXT NOT NULL,
    FOREIGN KEY (u_id) REFERENCES user (id)
);

CREATE TABLE link_song(
    link_number INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    place INTEGER,
    h_id INTEGER NOT NULL,
    u_id TEXT NOT NULL,
    playlist TEXT NOT NULL,

    CONSTRAINT  head_key
        FOREIGN KEY (h_id) 
        REFERENCES head_song (head_number) 
        ON DELETE CASCADE,

    FOREIGN KEY (u_id) REFERENCES user (id)
);