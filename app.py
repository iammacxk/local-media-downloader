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
        print(f"Found FFmpeg at custom path: {CUSTOM_FFMPEG_PATH}")
        return {'ffmpeg_location': CUSTOM_FFMPEG_PATH}
    
    if shutil.which('ffmpeg'):
        print("Found FFmpeg in system PATH")
        return {} 
        
    print("WARNING: FFmpeg not found! Merging video/audio might fail.")
    return {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_media():
    data = request.json
    url = data.get('url')
    format_type = data.get('type')

    if not url:
        return jsonify({'error': 'กรุณาใส่ลิงก์'}), 400

    # ฟังก์ชันสร้าง Options
    def create_opts(browser_source=None):
        opts = {
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            
            # --- 🚀 STEALTH TURBO MODE (สูตรหลบ Throttling) ---
            # ลดท่อลงเพื่อให้เสถียร + ปลอมตัวเป็นมือถือ
            'concurrent_fragment_downloads': 16, 
            'http_chunk_size': 10485760,         # ขอทีละ 10MB (ก้อนใหญ่ไป Server จะเมิน)
            'retries': 10,
            'file_access_retries': 5,
            
            # ✨ สูตรลับ: บังคับใช้ API ของ Android/iOS เพื่อเลี่ยงการโดนบีบความเร็ว
            'extractor_args': {'youtube': {'player_client': ['android', 'ios']}},
            # ---------------------------------------------
        }
        
        if browser_source:
            opts.update({'cookiesfrombrowser': (browser_source,)})

        opts.update(get_ffmpeg_opts())

        if format_type == 'mp3':
            opts.update({
                'format': 'bestaudio/best',
                'writethumbnail': True,
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    },
                    {'key': 'EmbedThumbnail'},
                    {'key': 'FFmpegMetadata'},
                ],
            })
        elif format_type == 'mp4':
            universal_format_rule = (
                'bestvideo[vcodec^=avc]+bestaudio[ext=m4a]/'  
                'bestvideo[vcodec^=h264]+bestaudio[ext=m4a]/' 
                'best[vcodec^=avc]/'                          
                'best[vcodec^=h264]/'                         
                'best[ext=mp4][vcodec!^=hevc][vcodec!^=hvc1]/' 
                'best[vcodec!^=hevc][vcodec!^=hvc1]/'          
                'best'                                         
            )
            opts.update({
                'format': universal_format_rule,
                'merge_output_format': 'mp4',
            })
        
        return opts

    # --- ระบบ Smart Switch (ปรับปรุงใหม่) ---
    success = False
    info = None
    last_error = None
    significant_error = None # เก็บ Error สำคัญ (เช่น Cookie Lock) ไว้แจ้งเตือน
    
    # ลำดับการหา Cookies: ลอง Edge ก่อน (มักจะปิดอยู่ ไม่ติดล็อก) -> Chrome -> Firefox -> None (Guest)
    browsers_to_try = [None]
    if 'twitter.com' in url or 'x.com' in url:
        browsers_to_try = ['edge', 'chrome', 'firefox', None]

    print(f"🚀 Processing: {url} (Stealth Turbo Mode)")

    for browser in browsers_to_try:
        try:
            current_opts = create_opts(browser_source=browser)
            # แก้ไข: แสดง Log เฉพาะตอนใช้ Browser (ไม่โชว์ Guest Mode แล้ว)
            if browser:
                print(f"👉 Trying method: {browser}...")
            
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                success = True
                if browser:
                    print(f"✅ Success using: {browser}")
                break 
                
        except Exception as e:
            err_msg = str(e).lower()
            last_error = e
            
            # เช็คว่าเป็นปัญหาเรื่อง Cookies หรือไม่
            is_cookie_issue = "cookie" in err_msg or "browser" in err_msg or "lock" in err_msg or "copy" in err_msg
            
            if is_cookie_issue:
                significant_error = e # จำ Error นี้ไว้ เพราะสำคัญกว่า "No video found"
            
            # ถ้าไม่ใช่ปัญหา Cookies และไม่ใช่ Guest Mode (เช่น ลิงก์เสียจริงๆ) ให้หยุดเลย
            if not is_cookie_issue and browser is not None:
                break
            
            # ถ้าเป็น Guest Mode แล้วพัง (No video found) ก็ให้วนลูปต่อไป (เผื่อจบ) หรือหยุดถ้าหมดตัวเลือกแล้ว

    if not success:
        # เลือก Error ที่ดีที่สุดมาแจ้งเตือน
        final_error = significant_error if significant_error else last_error
        error_text = str(final_error)
        
        if "sensitive" in error_text.lower():
            error_text = "⚠️ ติดเนื้อหา Sensitive (ต้องเปิดตั้งค่าใน X ก่อน)"
        elif "cookie" in error_text.lower() or "lock" in error_text.lower():
            error_text = "🔐 อ่าน Cookies ไม่ได้! (Chrome ติดล็อก / Edge ยังไม่ล็อกอิน) -> แนะนำให้ล็อกอิน X ใน Edge ทิ้งไว้แล้วปิด Edge ครับ"
        elif "no video" in error_text.lower():
            error_text = "❌ ไม่สามารถเข้าถึงวิดีโอได้ (X บล็อก Guest Mode) -> กรุณาล็อกอิน X ใน Edge ทิ้งไว้เพื่อใช้ยืนยันตัวตนครับ"
            
        return jsonify({'error': error_text}), 500

    # --- จัดการชื่อไฟล์ ---
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
        print(f"Error processing file info: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-file/<filename>')
def get_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    user_filename = request.args.get('title')
    if not user_filename:
        user_filename = filename

    try:
        return send_file(file_path, as_attachment=True, download_name=user_filename)
    except Exception as e:
        return str(e)

if __name__ == '__main__':
    app.run(debug=True, port=5000)