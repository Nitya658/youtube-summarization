from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, CouldNotRetrieveTranscript
from urllib.parse import urlparse, parse_qs
import re
from flask_cors import CORS
import requests
import time
import json
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)  # Enable CORS

# --- Gemini API Configuration ---
API_KEY = ""  # Insert API Key via environment/config
GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={API_KEY}"
# ---------------------------------


def get_video_id(url: str):
    """Extract YouTube video ID from URL."""
    query = urlparse(url).query
    params = parse_qs(query)
    if 'v' in params:
        return params['v'][0]

    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    return None


def get_transcript(video_id: str) -> str:
    """Fetch transcript in English, auto-generated English, or fallback captions. Includes auto-translate if non-English."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        return ' '.join([d['text'] for d in transcript_list])
    except NoTranscriptFound:
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['a.en'])
            return ' '.join([d['text'] for d in transcript_list])
        except NoTranscriptFound:
            # Try any available language and translate
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
            for transcript in transcripts:
                if transcript.language_code != 'en':
                    foreign_text = ' '.join([d['text'] for d in transcript.fetch()])
                    return translate_text(foreign_text, transcript.language)
            # Fallback to captions
            return get_fallback_captions(video_id)
        except Exception as e:
            raise Exception(f"Transcript retrieval error: {str(e)}")
    except TranscriptsDisabled:
        # Try fallback method if subtitles are disabled
        return get_fallback_captions(video_id)
    except CouldNotRetrieveTranscript as e:
        raise CouldNotRetrieveTranscript(f"Transcript Error: Could not retrieve transcript for video (ID: {video_id}). Reason: {str(e)}")


def get_fallback_captions(video_id: str) -> str:
    """Fallback: Try to fetch auto-generated captions via YouTube internal API."""
    try:
        url = f"https://video.google.com/timedtext?lang=en&v={video_id}"
        response = requests.get(url)
        if response.status_code == 200 and response.text.strip():
            root = ET.fromstring(response.text)
            texts = [node.text for node in root.findall('text') if node.text]
            return ' '.join(texts)
        else:
            raise NoTranscriptFound(f"No transcripts or captions available for video {video_id}.")
    except Exception as e:
        raise NoTranscriptFound(f"Fallback captions failed for video {video_id}: {str(e)}")


def translate_text(text: str, source_lang: str) -> str:
    """Translate text to English using Gemini API."""
    system_prompt = f"You are a professional translator. Translate the following text from {source_lang} to standard English."
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }

    try:
        response = requests.post(
            GEMINI_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload)
        )
        response.raise_for_status()
        result = response.json()
        return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', text)
    except Exception as e:
        return f"Translation failed: {str(e)}"


def get_summary_gemini(transcript: str) -> str:
    """Summarize transcript using Gemini API."""
    system_prompt = (
        "You are a concise summarization expert. Summarize the following YouTube video transcript "
        "into 3-5 key bullet points capturing main topics and conclusions."
    )
    payload = {
        "contents": [{"parts": [{"text": transcript}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }

    retries, delay = 5, 2
    for attempt in range(retries):
        try:
            response = requests.post(
                GEMINI_URL,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(payload)
            )
            response.raise_for_status()
            result = response.json()
            return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'Summary failed.')
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 500, 503] and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                raise Exception(f"Gemini API error: {e}")
        except Exception as e:
            raise Exception(f"Gemini API call failed: {e}")
    return "Summary generation failed."


@app.get('/summary')
def summary_api():
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided."}), 400

    video_id = get_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL format."}), 400

    try:
        transcript = get_transcript(video_id)
        if not transcript:
            return jsonify({"error": "Transcript is empty."}), 404

        summary = get_summary_gemini(transcript)
        return jsonify({"summary": summary}), 200
    except (NoTranscriptFound, TranscriptsDisabled, CouldNotRetrieveTranscript) as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"Internal Error: {e}")
        return jsonify({"error": "Internal error occurred. Ensure video has English captions."}), 500


if __name__ == '__main__':
    app.run(port=5000)