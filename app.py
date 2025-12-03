import os
import time
import shutil
import re # 🆕 เพิ่ม Library สำหรับจัดการข้อความ (RegEx)
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp
from yt_dlp.utils import DownloadError

app = Flask(__name__, template_folder='templates')

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# --- ตั้งค่า Path ของ FFmpeg ---
CUSTOM_FFMPEG_PATH = r"C:\ffmpeg\bin"
COOKIES_FILE = 'cookies.txt'

# --- Global Dictionary เก็บความคืบหน้า ---
download_progress = {}

def get_ffmpeg_opts():
    if os.path.exists(os.path.join(CUSTOM_FFMPEG_PATH, 'ffmpeg.exe')):
        return {'ffmpeg_location': CUSTOM_FFMPEG_PATH}
    if shutil.which('ffmpeg'):
        return {} 
    return {}

# 🆕 ฟังก์ชันล้างรหัสสี ANSI (แก้ภาษาแปลกๆ)
def clean_ansi(text):
    if not text: return ""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', str(text))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/progress', methods=['GET'])
def get_progress():
    req_id = request.args.get('id')
    if req_id and req_id in download_progress:
        return jsonify(download_progress[req_id])
    return jsonify({'percent': 0, 'status': 'waiting'})

@app.route('/fetch-info', methods=['POST'])
def fetch_info():
    data = request.json
    url = data.get('url')
    
    if not url: return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    use_cookie_file = False
    if os.path.exists(COOKIES_FILE):
        use_cookie_file = True
        print(f"🍪 Found {COOKIES_FILE}! Using external cookies.")

    browsers_to_try = [None]
    if not use_cookie_file and any(domain in url for domain in ['twitter.com', 'x.com', 'pornhub.com', 'youtube.com', 'youtu.be']):
        browsers_to_try = ['edge', 'chrome', 'firefox', None]

    result = None
    last_error = None
    
    if use_cookie_file:
        browsers_to_try = ['cookie_file']

    for browser in browsers_to_try:
        try:
            ydl_opts = {
                'quiet': True,
                'extract_flat': 'in_playlist', 
                'dump_single_json': True,
                'no_warnings': True,
                'noplaylist': False,
                'skip_download': True,
                'ignoreerrors': True,
                'playlist_items': '1:100',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': url,
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            }
            
            if browser == 'cookie_file':
                ydl_opts.update({'cookiefile': COOKIES_FILE})
            elif browser:
                ydl_opts.update({'cookiesfrombrowser': (browser,)})

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=False)
            break 
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if "closed file" in err_msg or "lock" in err_msg: time.sleep(1)
            is_cookie_issue = any(x in err_msg for x in ["closed file", "cookie", "browser", "lock", "copy", "decrypt", "dpapi"])
            if is_cookie_issue and browser != 'cookie_file' and browser is not None:
                continue
            if browser is None: break
            continue

    if not result:
        err_text = str(last_error)
        if "closed file" in err_text.lower() or "lock" in err_text.lower():
            err_text = "🔐 Browser ค้าง! (แนะนำ: ใช้ cookies.txt)"
        elif "sensitive" in err_text.lower():
            err_text = "⚠️ ติดเนื้อหา Sensitive (ต้องใช้ cookies.txt)"
        return jsonify({'error': err_text}), 500

    entries = []
    title = result.get('title', 'Unknown Title')
    is_playlist = False

    if 'entries' in result:
        is_playlist = True
        if not title: title = f"Playlist ({result.get('id', 'Unknown')})"
        for entry in result['entries']:
            if entry: 
                entries.append({
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('url') if entry.get('url') else entry.get('original_url'),
                    'id': entry.get('id'),
                    'duration': entry.get('duration') 
                })
    else:
        entries.append({
            'title': result.get('title'),
            'url': result.get('webpage_url', url),
            'id': result.get('id'),
            'duration': result.get('duration')
        })
        
    return jsonify({
        'success': True, 'is_playlist': is_playlist, 'title': title, 'entries': entries
    })

@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type')
    request_id = data.get('requestId')

    if not url: return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    use_cookie_file = False
    if os.path.exists(COOKIES_FILE):
        use_cookie_file = True

    # --- Hook Function: ล้างรหัสสีก่อนส่ง ---
    def progress_hook(d):
        if request_id:
            if d['status'] == 'downloading':
                # ล้างรหัสสีออกจากข้อความ
                p_str = clean_ansi(d.get('_percent_str', '0%')).replace('%','')
                try:
                    percent = float(p_str)
                except:
                    percent = 0
                
                speed = clean_ansi(d.get('_speed_str', 'N/A'))
                eta = clean_ansi(d.get('_eta_str', 'N/A'))
                
                download_progress[request_id] = {
                    'percent': percent,
                    'speed': speed,
                    'eta': eta,
                    'status': 'downloading'
                }
            elif d['status'] == 'finished':
                download_progress[request_id] = {
                    'percent': 100,
                    'speed': '-',
                    'eta': '-',
                    'status': 'processing'
                }

    def create_opts(browser_source=None):
        opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
            'trim_file_name': 200,
            'restrictfilenames': False,
            'quiet': True,
            'no_warnings': True,
            'concurrent_fragment_downloads': 16, 
            'http_chunk_size': 10485760,
            'retries': 10,
            'file_access_retries': 5,
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': url,
            },
            'progress_hooks': [progress_hook],
        }
        
        if browser_source == 'cookie_file':
            opts.update({'cookiefile': COOKIES_FILE})
        elif browser_source:
            opts.update({'cookiesfrombrowser': (browser_source,)})

        opts.update(get_ffmpeg_opts())

        if format_type == 'mp3':
            opts.update({
                'format': 'bestaudio/best',
                'writethumbnail': True,
                'postprocessors': [
                    {'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'},
                    {'key': 'EmbedThumbnail'},{'key': 'FFmpegMetadata'},
                ],
            })
        elif format_type == 'mp4':
            opts.update({
                'format': 'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
            })
        
        return opts

    success = False
    info = None
    last_error = None
    
    if use_cookie_file:
        browsers_to_try = ['cookie_file']
    else:
        browsers_to_try = [None]
        if any(domain in url for domain in ['twitter.com', 'x.com', 'pornhub.com', 'youtube.com', 'youtu.be']):
            browsers_to_try = ['edge', 'chrome', 'firefox', None]

    print(f"🚀 Processing: {url} [ID: {request_id}]")
    if use_cookie_file: print("🍪 Using cookies.txt mode")

    if request_id:
        download_progress[request_id] = {'percent': 0, 'speed': 'Starting...', 'status': 'starting'}

    final_filename_on_disk = None 

    for browser in browsers_to_try:
        try:
            current_opts = create_opts(browser_source=browser)
            if browser and browser != 'cookie_file': print(f"👉 Trying method: {browser}...")
            
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info: target_info = info['entries'][0]
                else: target_info = info
                
                temp_path = ydl.prepare_filename(target_info)
                base, _ = os.path.splitext(temp_path)
                if format_type == 'mp3': final_path = base + '.mp3'
                else: final_path = base + '.mp4'
                
                final_filename_on_disk = os.path.basename(final_path)
                success = True
                if browser: print(f"✅ Success using: {browser}")
                break 
        except Exception as e:
            err_msg = str(e).lower()
            last_error = e
            if "closed file" in err_msg: time.sleep(1)
            is_cookie_issue = any(x in err_msg for x in ["closed file", "cookie", "browser", "lock", "copy", "decrypt", "dpapi"])
            if is_cookie_issue and browser != 'cookie_file' and browser is not None:
                print(f"⚠️ Cookie error in {browser}, skipping...")
                continue
            break

    if request_id and request_id in download_progress:
        del download_progress[request_id]

    if not success:
        error_text = str(last_error)
        if "closed file" in error_text.lower() or "lock" in error_text.lower():
            error_text = "🔐 Browser ค้าง! (ลองใช้ไฟล์ cookies.txt เพื่อแก้ปัญหานี้)"
        elif "sensitive" in error_text.lower():
            error_text = "⚠️ ติดเนื้อหา Sensitive (กรุณาใช้ cookies.txt ที่ล็อกอินแล้ว)"
        return jsonify({'error': error_text}), 500

    try:
        filename_on_disk = final_filename_on_disk
        from urllib.parse import quote
        encoded_title = quote(filename_on_disk)

        return jsonify({
            'success': True,
            'filename': filename_on_disk,
            'download_url': f'/get-file/{filename_on_disk}?title={encoded_title}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get-file/<filename>')
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    user_filename = request.args.get('title') or filename
    try: return send_file(file_path, as_attachment=True, download_name=user_filename)
    except Exception as e: return str(e)

if __name__ == '__main__':
    app.run(debug=True, port=5000)