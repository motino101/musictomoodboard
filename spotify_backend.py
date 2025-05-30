#!/usr/bin/env python3
"""
Simple Spotify Audio Features Backend
A Flask API that fetches audio features and analysis from Spotify Web API
"""

import os
import json
import base64
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Spotify API Configuration
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env file")

SPOTIFY_API_BASE = 'https://api.spotify.com/v1'
SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'

# In-memory token storage (use Redis/database in production)
access_token = None
token_expires_at = None

def get_spotify_token():
    """Get access token using client credentials flow"""
    global access_token, token_expires_at
    
    # Check if token is still valid
    if access_token and token_expires_at and datetime.now() < token_expires_at:
        return access_token
    
    # Get new token
    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {"grant_type": "client_credentials"}
    
    try:
        logger.info(f"Attempting to get Spotify token with Client ID: {SPOTIFY_CLIENT_ID[:5]}...")
        response = requests.post(SPOTIFY_TOKEN_URL, headers=headers, data=data)
        
        if response.status_code != 200:
            logger.error(f"Spotify token request failed with status {response.status_code}")
            logger.error(f"Response content: {response.text}")
            response.raise_for_status()
        
        token_data = response.json()
        access_token = token_data["access_token"]
        expires_in = token_data["expires_in"]
        token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)  # 60s buffer
        
        logger.info("Successfully obtained Spotify access token")
        return access_token
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get Spotify token: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Error response: {e.response.text}")
        return None

def make_spotify_request(endpoint):
    """Make authenticated request to Spotify API"""
    token = get_spotify_token()
    if not token:
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{SPOTIFY_API_BASE}/{endpoint}"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Spotify API request failed: {e}")
        return None

def extract_track_id(spotify_url_or_id):
    """Extract track ID from Spotify URL or return if already an ID"""
    if spotify_url_or_id.startswith('https://open.spotify.com/track/'):
        return spotify_url_or_id.split('/')[-1].split('?')[0]
    elif spotify_url_or_id.startswith('spotify:track:'):
        return spotify_url_or_id.split(':')[-1]
    else:
        # Assume it's already a track ID
        return spotify_url_or_id

@app.route('/', methods=['GET'])
def home():
    """API documentation endpoint"""
    return jsonify({
        "message": "Spotify Audio Features API",
        "endpoints": {
            "/track/<track_id_or_url>": "Get basic track info",
            "/features/<track_id_or_url>": "Get audio features for a track",
            "/analysis/<track_id_or_url>": "Get detailed audio analysis for a track",
            "/complete/<track_id_or_url>": "Get track info, features, and analysis combined",
            "/search?q=<query>": "Search for tracks"
        },
        "example_track_id": "4iV5W9uYEdYUVa79Axb7Rh",
        "example_usage": "/features/4iV5W9uYEdYUVa79Axb7Rh"
    })

@app.route('/track/<track_identifier>', methods=['GET'])
def get_track_info(track_identifier):
    """Get basic track information"""
    track_id = extract_track_id(track_identifier)
    
    data = make_spotify_request(f"tracks/{track_id}")
    if not data:
        return jsonify({"error": "Failed to fetch track data"}), 500
    
    # Extract relevant track info
    track_info = {
        "id": data["id"],
        "name": data["name"],
        "artists": [artist["name"] for artist in data["artists"]],
        "album": data["album"]["name"],
        "duration_ms": data["duration_ms"],
        "popularity": data["popularity"],
        "preview_url": data.get("preview_url"),
        "external_urls": data["external_urls"]
    }
    
    return jsonify(track_info)

@app.route('/features/<track_identifier>', methods=['GET'])
def get_audio_features(track_identifier):
    """Get audio features for a track"""
    track_id = extract_track_id(track_identifier)
    
    data = make_spotify_request(f"audio-features/{track_id}")
    if not data:
        return jsonify({"error": "Failed to fetch audio features"}), 500
    
    return jsonify(data)

@app.route('/analysis/<track_identifier>', methods=['GET'])
def get_audio_analysis(track_identifier):
    """Get detailed audio analysis for a track"""
    track_id = extract_track_id(track_identifier)
    
    data = make_spotify_request(f"audio-analysis/{track_id}")
    if not data:
        return jsonify({"error": "Failed to fetch audio analysis"}), 500
    
    return jsonify(data)

@app.route('/complete/<track_identifier>', methods=['GET'])
def get_complete_track_data(track_identifier):
    """Get track info, audio features, and analysis combined"""
    track_id = extract_track_id(track_identifier)
    
    # Fetch all data in parallel would be better, but keeping it simple
    track_data = make_spotify_request(f"tracks/{track_id}")
    features_data = make_spotify_request(f"audio-features/{track_id}")
    analysis_data = make_spotify_request(f"audio-analysis/{track_id}")
    
    if not all([track_data, features_data, analysis_data]):
        return jsonify({"error": "Failed to fetch complete track data"}), 500
    
    # Combine all data
    complete_data = {
        "track_info": {
            "id": track_data["id"],
            "name": track_data["name"],
            "artists": [artist["name"] for artist in track_data["artists"]],
            "album": track_data["album"]["name"],
            "duration_ms": track_data["duration_ms"],
            "popularity": track_data["popularity"],
            "preview_url": track_data.get("preview_url"),
            "external_urls": track_data["external_urls"]
        },
        "audio_features": features_data,
        "audio_analysis": {
            "meta": analysis_data.get("meta", {}),
            "track": analysis_data.get("track", {}),
            "bars": len(analysis_data.get("bars", [])),
            "beats": len(analysis_data.get("beats", [])),
            "sections": len(analysis_data.get("sections", [])),
            "segments": len(analysis_data.get("segments", [])),
            "tatums": len(analysis_data.get("tatums", []))
        }
    }
    
    return jsonify(complete_data)

@app.route('/search', methods=['GET'])
def search_tracks():
    """Search for tracks"""
    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    limit = min(int(request.args.get('limit', 10)), 50)  # Max 50
    
    endpoint = f"search?q={query}&type=track&limit={limit}"
    data = make_spotify_request(endpoint)
    
    if not data:
        return jsonify({"error": "Failed to search tracks"}), 500
    
    # Simplify the response
    tracks = []
    for item in data["tracks"]["items"]:
        tracks.append({
            "id": item["id"],
            "name": item["name"],
            "artists": [artist["name"] for artist in item["artists"]],
            "album": item["album"]["name"],
            "popularity": item["popularity"],
            "preview_url": item.get("preview_url"),
            "external_urls": item["external_urls"]
        })
    
    return jsonify({
        "tracks": tracks,
        "total": data["tracks"]["total"]
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Check for required environment variables
    if SPOTIFY_CLIENT_ID == 'your_client_id_here' or SPOTIFY_CLIENT_SECRET == 'your_client_secret_here':
        print("⚠️  WARNING: Please set your Spotify API credentials!")
        print("Set environment variables:")
        print("export SPOTIFY_CLIENT_ID='your_actual_client_id'")
        print("export SPOTIFY_CLIENT_SECRET='your_actual_client_secret'")
        print("\nGet credentials at: https://developer.spotify.com/dashboard")
        print("\nStarting server anyway for testing...")
    
    print("🎵 Starting Spotify Audio Features API...")
    print("📖 Visit http://localhost:5000 for API documentation")
    print("🔍 Example: http://localhost:5000/features/4iV5W9uYEdYUVa79Axb7Rh")
    
    # Install required packages if not already installed
    try:
        import flask
        import requests
    except ImportError:
        print("\n📦 Install required packages with:")
        print("pip install flask requests")
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=5050)