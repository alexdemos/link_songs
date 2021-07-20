"""
Prerequisites
    pip3 install spotipy Flask Flask-Session
    // from your [app settings](https://developer.spotify.com/dashboard/applications)
    SET SPOTIPY_CLIENT_ID=client_id_here
    SET SPOTIPY_CLIENT_SECRET=client_secret_here
    SET SPOTIPY_REDIRECT_URI='http://127.0.0.1:5000' // must contain a port
    // SPOTIPY_REDIRECT_URI must be added to your [app settings](https://developer.spotify.com/dashboard/applications)
    OPTIONAL
    // in development environment for debug output
    export FLASK_ENV=development
    // so that you can invoke the app outside of the file's directory include
    export FLASK_APP=/path/to/spotipy/examples/app.py
 
    // on Windows, use `SET` instead of `export`
Run app.py
    python3 app.py OR python3 -m flask run
    NOTE: If receiving "port already in use" error, try other ports: 5000, 8090, 8888, etc...
        (will need to be updated in your Spotify app and SPOTIPY_REDIRECT_URI variable)
"""

import os
from flask import Flask, session, request, redirect, render_template, url_for, Blueprint, flash, g
from flask_session import Session
from dotenv import load_dotenv
import spotipy as sp
import uuid
import json
from werkzeug.security import check_password_hash, generate_password_hash
import time
import threading
import ctypes

from .db import get_db

bp = Blueprint('main', __name__, url_prefix='/')
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'

Session(app)
PORT = 5000
SCOPE = 'user-read-currently-playing playlist-modify-private playlist-modify-public streaming user-modify-playback-state user-read-playback-state'

# os.environ['SPOTIPY_CLIENT_ID'] = os.getenv('SPOTIPY_CLIENT_ID')
# os.environ['SPOTIPY_CLIENT_SECRET'] = os.getenv('SPOTIPY_CLIENT_SECRET')
# os.environ['SPOTIPY_REDIRECT_URI']= 'http://127.0.0.1:5000'
os.environ['SPOTIPY_REDIRECT_URI'] = 'https://spotify-linked-songs.herokuapp.com/'

caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)


def session_cache_path():
    return caches_folder + session.get('uuid')


@bp.route('/')
def index():
    if not session.get('uuid'):
        # Step 1. Visitor is unknown, give random ID
        session['uuid'] = str(uuid.uuid4())

    duplicate = False
    if not session.get('duplicate'):
        session['duplicate'] = False

    if session['duplicate'] == True:
        duplicate = True
        session['duplicate'] = False

    

    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(scope=SCOPE,
                                          cache_handler=cache_handler,
                                          show_dialog=True)
    if request.args.get("code"):
        # Step 3. Being redirected from Spotify auth page
        auth_manager.get_access_token(request.args.get("code"))
        return redirect('/')

    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # Step 2. Display sign in link when no token
        auth_url = auth_manager.get_authorize_url()
        return render_template('sign_in.html', auth_url=auth_url)

    # Step 4. Signed in, display data
    spotify = sp.Spotify(auth_manager=auth_manager)

    username = spotify.me()['display_name']
    u_id = spotify.me()['id']

    playlists = spotify.current_user_playlists()['items']
    if 'current_playlist' not in session or 'current_playlist_id' not in session:
        session['current_playlist'] = playlists[0]['name']
        session['current_playlist_id'] = playlists[0]['id']
        session['current_playlist_uri'] = playlists[0]['uri']

    db = get_db()

    user = db.execute(
        'SELECT id FROM user WHERE id = (?)', (u_id,)
    ).fetchall()

    if len(user) == 0:
        db.execute(
            'INSERT INTO user (id) VALUES (?)', (u_id,)
        )
        db.commit()

    session['user'] = u_id

    head_songs = get_head_song_with_pl(session['user'], session['current_playlist'])
    link_songs = get_link_song_with_pl(session['user'], session['current_playlist'])
    return render_template('index.html', name=username, head_songs=head_songs, link_songs=link_songs, duplicate=duplicate)

@bp.route('<id>/delete', methods=('POST',))
def delete(id):
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')

    spotify = sp.Spotify(auth_manager=auth_manager)
    song = get_head_song(id)

    db = get_db()
    db.execute(
        'DELETE FROM link_song '
        'WHERE h_id = ? and u_id = ?',
        (song['head_number'], song['u_id'])
    )
    db.execute(
        'DELETE FROM head_song '
        'WHERE head_number = ? and u_id = ?',
        (song['head_number'], song['u_id'])
    )
    db.commit()

    spotify.user_playlist_remove_all_occurrences_of_tracks(session['user'],session['current_playlist_id'], [song['id']])

    head_songs = get_head_song_with_pl(session['user'], session['current_playlist'])
    link_songs = get_link_song_with_pl(session['user'], session['current_playlist'])
    return render_template('index.html', head_songs=head_songs, link_songs=link_songs, name=session['user'])

@bp.route('<id>/link_delete', methods=('POST',))
def link_delete(id):
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')

    spotify = sp.Spotify(auth_manager=auth_manager)
    song = get_link_song(id)

    db = get_db()
    db.execute(
        'DELETE FROM link_song '
        'WHERE link_number = ? and u_id = ?',
        (song['link_number'], song['u_id'])
    )
    db.commit()

    head_songs = get_head_song_with_pl(session['user'], session['current_playlist'])
    link_songs = get_link_song_with_pl(session['user'], session['current_playlist'])
    return render_template('index.html', head_songs=head_songs, link_songs=link_songs, name=session['user'])

@bp.route('/sign_out')
def sign_out():
    try:
        # Remove the CACHE file (.cache-test) so that a new user can authorize.
        os.remove(session_cache_path())
        session.clear()
    except OSError as e:
        print("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/')

@bp.route('/search', methods=('GET', 'POST'))
def search():
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = sp.Spotify(auth_manager=auth_manager)
    s = []

    if request.method == 'POST':

        if 'search' in request.form:
            q = request.form['search']
            session['song_name'] = q
            songs = spotify.search(q)
            s = songs['tracks']['items']

        elif 'value' in request.form:
            if request.form['value'] != '':
                session['song_value'] = request.form['value']
                sl = spotify.search(session['song_name'])
                head_song = sl['tracks']['items'][int(request.form['value'])]
                head_uri = head_song['uri']
                head_title = head_song['name']
                head_artist = head_song['artists'][0]['name']
                db = get_db()
                check_song = db.execute('SELECT id FROM head_song WHERE id = ? AND  playlist = ? ', (head_uri,session['current_playlist'])).fetchall()

                if len(check_song) == 0:
                    db.execute(
                        'INSERT INTO head_song (id, title, artist, u_id, playlist)'
                        'VALUES (?,?,?,?,?)', (head_uri, head_title, head_artist,
                                            session['user'], session['current_playlist'])

                    )
                    db.commit()

                    spotify.user_playlist_remove_all_occurrences_of_tracks(session['user'],session['current_playlist_id'],[head_uri])
                    spotify.user_playlist_add_tracks(session['user'],session['current_playlist_id'],[head_uri])
                else:
                    session['duplicate'] = True

    return render_template('search.html', songs=s)


@bp.route('<id>/link', methods=('GET', 'POST'))
def link(id):
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = sp.Spotify(auth_manager=auth_manager)
    s = []

    if request.method == 'POST':

        if 'link' in request.form:
            q = request.form['link']
            session['song_name'] = q
            songs = spotify.search(q)
            s = songs['tracks']['items']

        elif 'value' in request.form:
            if request.form['value'] != '':
                session['song_value'] = request.form['value']
                sl = spotify.search(session['song_name'])
                link_song = sl['tracks']['items'][int(request.form['value'])]
                link_uri = link_song['uri']
                link_title = link_song['name']
                link_artist = link_song['artists'][0]['name']
                db = get_db()
                db.execute(
                    'INSERT INTO link_song (id, title, artist, u_id, h_id, playlist)'
                    'VALUES (?,?,?,?,?,?)',
                    (link_uri, link_title, link_artist, session['user'], id, session['current_playlist'])
                )
                db.commit()

    return render_template('link.html', songs=s, h_id=id)


@bp.route('/play', methods=('GET', 'POST'))
def play():
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = sp.Spotify(auth_manager=auth_manager)
    devices = spotify.devices()['devices']
    
    db = get_db()
    head_songs = get_head_song_with_pl(session['user'], session['current_playlist'])
    link_songs = get_link_song_with_pl(session['user'], session['current_playlist'])
    song_dict = create_dict(head_songs, link_songs)

    if 'base_thread_count' not in session:
        session['base_thread_count'] = threading.activeCount()

    caught_error = False

    class play_thread(threading.Thread):
        def __init__(self, name, song_dict, spotify):
            threading.Thread.__init__(self)
            self.threadID = name
            self.song_dict = song_dict
            self.spotify = spotify

        def run(self):
                play_songs(self.song_dict, self.spotify)

        def get_id(self):
        # returns id of the respective thread
            if hasattr(self, '_thread_id'):
                return self._thread_id
            for id, thread in threading._active.items():
                if thread is self:
                    return id

        def raise_exception(self):
            thread_id = ctypes.c_long(self.get_id())
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id,
                ctypes.py_object(SystemExit))
            if res > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)

    thread = play_thread('Thread-1', song_dict, spotify)

    if 'device_id' not in session:
        first_device = spotify.devices()['devices'][0]
        session['device_id'] = first_device['id']
        session['device_name'] = first_device['name']

    print(threading.activeCount() - session['base_thread_count'])
    if request.method == "POST":
        if 'submit' in request.form: 
            if threading.activeCount() - session['base_thread_count'] == 0:
                print('Entered')
                if spotify.current_playback() == None:
                    try:
                        spotify.shuffle(True, session['device_id'])
                        spotify.start_playback(device_id=session['device_id'], context_uri=session['current_playlist_uri'])
                        thread.start()
                    except sp.exceptions.SpotifyException:
                        caught_error = True
                        return render_template('play.html', devices=devices, device_name=session['device_name'], caught_error=caught_error)
                elif spotify.current_playback()['is_playing'] == False:
                    try:
                        spotify.shuffle(True, session['device_id'])
                        spotify.start_playback(device_id=session['device_id'], context_uri=session['current_playlist_uri'])
                        thread.start()
                    except sp.exceptions.SpotifyException:
                        caught_error = True
                        return render_template('play.html', devices=devices, device_name=session['device_name'], caught_error=caught_error)
                else:
                    thread.start()
                session['thread_name'] = thread.getName()
            
        elif 'stop' in request.form:
            if spotify.current_playback()['is_playing'] == True:
                try:
                    spotify.pause_playback(device_id=session['device_id'])
                except sp.exceptions.SpotifyException:
                    caught_error = True
                    return render_template('play.html', devices=devices, device_name=session['device_name'], caught_error=caught_error)
            play_thread = get_thread_by_name(session['thread_name'])
            if play_thread:
                play_thread.raise_exception()
                play_thread.join()
    
        elif 'devices' in request.form:
            device_num = int(request.form['devices'])
            session['device_id'] = devices[device_num]['id']
            session['device_name'] = devices[device_num]['name']

    return render_template('play.html', devices=devices, device_name=session['device_name'], caught_error=caught_error)


@bp.route('/change', methods=('GET', 'POST'))
def change():
    cache_handler = sp.cache_handler.CacheFileHandler(
        cache_path=session_cache_path())
    auth_manager = sp.oauth2.SpotifyOAuth(cache_handler=cache_handler)
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        return redirect('/')
    spotify = sp.Spotify(auth_manager=auth_manager)
    playlists = spotify.current_user_playlists()['items']

    chosen_playlist = session['current_playlist']
    if 'value' in request.form:
        pl_value = int(request.form['value'])
        chosen_playlist = playlists[pl_value]
        session['current_playlist'] = chosen_playlist['name']
        session['current_playlist_id'] = chosen_playlist['id']
        session['current_playlist_uri'] = chosen_playlist['uri']
        print(session['current_playlist'])

    return render_template('change.html', playlists=playlists)


def create_dict(head_songs, link_songs):
    song_dict = {}

    for head in head_songs:
        head_id = head['id']
        song_dict[head_id] = []
        for link in link_songs:
            if link['h_id'] == head['head_number']:
                link_id = link['id']
                song_dict[head_id].append(link_id)

    return song_dict


def play_songs(song_dict, spotify): 
    time.sleep(2)
    last_song = ''
    while True:
        track = spotify.current_user_playing_track()
        while track == None:
            track = spotify.current_user_playing_track()
        if track != None:
            current = track['item']['uri']

        if current in song_dict and current != last_song:
            for link_song in song_dict[current]:
                spotify.add_to_queue(link_song)

        if current != last_song:
            last_song = current

        time.sleep(2)

def get_thread_by_name(name):
    for t in threading.enumerate():
        if t.getName() == name:
            return t
    return None

def get_head_song_with_pl(user, pl):
    head_songs = get_db().execute('SELECT head_number, title, artist, id FROM head_song WHERE u_id = ? AND playlist = ?',
                                  (user, pl)).fetchall()
    return head_songs


def get_link_song_with_pl(user, pl):
    link_songs = get_db().execute(
        'SELECT link_number, title, artist, id, h_id FROM link_song WHERE u_id = ? AND playlist = ?', (user, pl)).fetchall()
    return link_songs

def get_head_song(h_id):
    song = get_db().execute(
        'SELECT h.id, h.title, h.artist, h.u_id, h.head_number '
        'FROM head_song h JOIN user u ON h.u_id = u.id '
        'WHERE h.head_number = ? and u.id = ?',
        (h_id, session['user'])
    ).fetchone()

    return song

def get_link_song(l_id):
    song = get_db().execute(
        'SELECT l.id, l.title, l.artist, l.u_id, l.link_number '
        'FROM link_song l JOIN user u ON l.u_id = u.id '
        'WHERE l.link_number = ? and u.id = ?',
        (l_id, session['user'])
    ).fetchone()

    return song

if __name__ == "__main__":
    app.run()
