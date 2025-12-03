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

# --- 🆕 API: ดึงข้อมูล Video/Playlist (ปรับปรุงใหม่) ---
@app.route('/fetch-info', methods=['POST'])
def fetch_info():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    try:
        # ตั้งค่าการดึงข้อมูล
        ydl_opts = {
            'quiet': True,
            'extract_flat': True, # เปลี่ยนเป็น True เพื่อให้ดึง Mix ได้แม่นยำขึ้น
            'dump_single_json': True,
            'no_warnings': True,
            'noplaylist': False, # สำคัญ: บังคับให้มองหา Playlist ก่อน
        }
        
        # ถ้าเป็น X/Twitter ให้ลองใช้ Cookies จาก Edge
        if 'twitter.com' in url or 'x.com' in url:
             ydl_opts.update({'cookiesfrombrowser': ('edge',)})

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)

        entries = []
        title = result.get('title', 'Unknown Title')
        is_playlist = False

        # Logic แยกแยะว่าเป็น Playlist หรือ Video เดียว
        if 'entries' in result:
            is_playlist = True
            # YouTube Mix มักจะไม่มี Title ที่ชัดเจนในบางที
            if not title and 'id' in result:
                title = f"Playlist: {result['id']}"
                
            for entry in result['entries']:
                if entry: 
                    # กรองเฉพาะรายการที่ดูได้ (บางที Mix มีรายการที่เป็น None)
                    entries.append({
                        'title': entry.get('title', 'Unknown Title'),
                        'url': entry.get('url') if entry.get('url') else entry.get('original_url'),
                        'id': entry.get('id'),
                        'duration': entry.get('duration')
                    })
        else:
            # กรณีเป็นคลิปเดียว
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

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API เดิม: ดาวน์โหลดไฟล์ (เวอร์ชันสมบูรณ์) ---
@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type')

    if not url: return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    # ฟังก์ชันสร้าง Options
    def create_opts(browser_source=None):
        opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            # Stealth Turbo Mode
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

    # Smart Switch Logic
    success = False
    info = None
    last_error = None
    browsers_to_try = [None]
    if 'twitter.com' in url or 'x.com' in url:
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
            error_text = "🔐 อ่าน Cookies ไม่ได้! (ลองล็อกอิน X ใน Edge ทิ้งไว้)"
        elif "no video" in error_text.lower():
            error_text = "❌ X บล็อก Guest Mode (ลองล็อกอิน X ใน Edge ทิ้งไว้)"
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