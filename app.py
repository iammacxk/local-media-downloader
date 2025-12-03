import os
import time
import shutil
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp
from yt_dlp.utils import DownloadError

app = Flask(__name__, template_folder='templates')

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# --- ตั้งค่า Path ของ FFmpeg ---
CUSTOM_FFMPEG_PATH = r"C:\ffmpeg\bin"

def get_ffmpeg_opts():
    if os.path.exists(os.path.join(CUSTOM_FFMPEG_PATH, 'ffmpeg.exe')):
        return {'ffmpeg_location': CUSTOM_FFMPEG_PATH}
    if shutil.which('ffmpeg'):
        return {} 
    return {}

@app.route('/')
def index():
    return render_template('index.html')

# --- 🆕 API: ดึงข้อมูล Video/Playlist (Turbo Fetch) ---
@app.route('/fetch-info', methods=['POST'])
def fetch_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    # กำหนดเบราว์เซอร์ที่จะลองใช้ (สำหรับเว็บที่ต้องล็อกอิน)
    browsers_to_try = [None]
    if any(domain in url for domain in ['twitter.com', 'x.com', 'pornhub.com']):
        browsers_to_try = ['edge', 'chrome', 'firefox', None]

    result = None
    last_error = None

    for browser in browsers_to_try:
        try:
            # --- ⚡ LIGHTWEIGHT SETTINGS (เน้นดึงข้อมูลเร็วที่สุด) ---
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,       # ดึงแค่ Metadata พื้นฐาน (Title/ID) ไม่เจาะลึก (เร็วมาก)
                'dump_single_json': True,
                'no_warnings': True,
                'noplaylist': False,        # อนุญาตให้ดึง Playlist
                'skip_download': True,      # ย้ำว่าห้ามโหลดไฟล์
                'ignoreerrors': True,       # ข้ามคลิปที่เสีย/ดูไม่ได้ทันที ไม่ต้องรอ Retry
                'playlist_items': '1:2000', # จำกัดไว้ 2000 เพลงแรก (กันเครื่องค้างถ้าเจอ Playlist เป็นหมื่น)
            }
            
            if browser:
                ydl_opts.update({'cookiesfrombrowser': (browser,)})

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=False)
            
            break # สำเร็จแล้วออกเลย
            
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            # ถ้าเป็นปัญหา Cookies ให้ลองเบราว์เซอร์อื่นต่อ
            if "cookie" in err_msg or "browser" in err_msg or "lock" in err_msg or "copy" in err_msg:
                if browser is not None: continue
            break # ถ้าเป็น Error อื่นหยุดเลย

    if not result:
        return jsonify({'error': str(last_error)}), 500

    entries = []
    title = result.get('title', 'Unknown Title')
    is_playlist = False

    # Logic แยกแยะ Playlist
    if 'entries' in result:
        is_playlist = True
        if not title and 'id' in result:
            title = f"Playlist: {result['id']}"
            
        for entry in result['entries']:
            if entry: 
                entries.append({
                    'title': entry.get('title', 'Unknown Title'),
                    'url': entry.get('url') if entry.get('url') else entry.get('original_url'),
                    'id': entry.get('id'),
                    # หมายเหตุ: extract_flat: True อาจจะไม่ได้ duration มาในบางเว็บ เพื่อแลกกับความเร็ว
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
        'success': True,
        'is_playlist': is_playlist,
        'title': title,
        'entries': entries
    })

# --- API เดิม: ดาวน์โหลดไฟล์ ---
@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type')

    if not url: return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    def create_opts(browser_source=None):
        opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            # Stealth Turbo Mode for Download
            'concurrent_fragment_downloads': 16, 
            'http_chunk_size': 10485760,
            'retries': 10,
            'file_access_retries': 5,
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
        }
        
        if browser_source:
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
    browsers_to_try = [None]
    
    if any(domain in url for domain in ['twitter.com', 'x.com', 'pornhub.com']):
        browsers_to_try = ['edge', 'chrome', 'firefox', None]

    print(f"🚀 Processing: {url}")

    for browser in browsers_to_try:
        try:
            current_opts = create_opts(browser_source=browser)
            if browser: print(f"👉 Trying method: {browser}...")
            
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                success = True
                if browser: print(f"✅ Success using: {browser}")
                break 
        except Exception as e:
            err_msg = str(e).lower()
            last_error = e
            is_cookie_issue = "cookie" in err_msg or "browser" in err_msg or "lock" in err_msg or "copy" in err_msg
            if not is_cookie_issue and browser is not None:
                break

    if not success:
        error_text = str(last_error)
        if "sensitive" in error_text.lower():
            error_text = "⚠️ ติดเนื้อหา Sensitive (ต้องเปิดตั้งค่าใน X ก่อน)"
        elif "cookie" in error_text.lower():
            error_text = "🔐 อ่าน Cookies ไม่ได้! (ลองล็อกอิน X/Pornhub ใน Edge ทิ้งไว้)"
        elif "no video" in error_text.lower():
            error_text = "❌ ไม่สามารถเข้าถึงวิดีโอได้ (ลองล็อกอินใน Edge ทิ้งไว้)"
        return jsonify({'error': error_text}), 500

    try:
        if format_type == 'mp3': ext = '.mp3'
        else: ext = '.mp4'

        if 'entries' in info:
            video_info = info['entries'][0]
            file_id = video_info.get('id')
            video_title = video_info.get('title')
        else:
            file_id = info.get('id')
            video_title = info.get('title')
        
        filename_on_disk = f"{file_id}{ext}"
        safe_title = "".join([c for c in video_title if c not in r'<>:"/\|?*'])
        download_filename = f"{safe_title}{ext}"
        from urllib.parse import quote
        encoded_title = quote(download_filename)

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