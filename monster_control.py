import asyncio
import aiohttp
import json
import time
import subprocess
import hashlib

# =========================================================
#  CONFIGURATION AREA
# =========================================================

# رابط ملف الداتا المباشر
JSON_DB_URL = "https://oma-server.site/omar/db.json"

# هام جداً: مفتاح الاستضافة (يجب أن يطابق المفتاح الذي أدخلته في لوحة PHP)
# غير هذا المفتاح في كل استضافة جديدة تستخدمها
MY_NODE_KEY = "omar_094_key"  # <--- مثال: غيره إلى أي كلمة وادخلها في اللوحة

# =========================================================

running_streams = {} # { 'stream_id': { 'process': proc, 'hash': 'abc...' } }

async def fetch_db_data():
    """Download database json"""
    try:
        ts = int(time.time())
        url = f"{JSON_DB_URL}?t={ts}" # No Cache
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, ssl=False) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    return data.get('streams', {})
                return {}
    except Exception as e:
        print(f"⚠️ Net Error: {e}")
        return {}

def build_ffmpeg_cmd(config):
    """بناء أوامر FFmpeg بناءً على المدخلات ودعم كافة المنصات"""
    input_url = config['input']
    rtmp_url = config['server'].rstrip('/')
    key = config['stream_key']
    quality = config['quality']
    overlay = config.get('overlay', '')
    
    # تحديد الرابط النهائي بشكل صحيح (يدعم rtmps)
    separator = "/"
    if "youtube" in rtmp_url: separator = "/" # يوتيوب يحب /
    output = f"{rtmp_url}{separator}{key}"
    if "facebook" in rtmp_url: output = f"{rtmp_url}" # فيسبوك يضع المفتاح ضمن الرابط احيانا ولكن الافتراضي كسر هذا
    if not output.startswith('rtmp'): # في حالة الكستم ربما المستخدم وضع الرابط كاملا
        pass 
        
    # الأمر الأساسي هو إعادة تشكيل flv
    # هذه الإعدادات تعمل مع فيسبوك ويوتيوب وكيك بشكل ممتاز
    output = f"{rtmp_url}/{key}"
    
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    
    # تحسين الدخل HTTP
    if input_url.startswith('http'):
        cmd.extend([
            '-user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
            '-timeout', '10000000'
        ])
    
    # Loop for videos
    if not input_url.startswith(('rtmp', 'rtsp')):
        cmd.extend(['-stream_loop', '-1'])
    
    cmd.extend(['-re', '-i', input_url])

    # منطق الاوفرلاي والجودة
    has_overlay = (quality in ['custom', 'high_quality']) and (len(overlay) > 5)

    if has_overlay:
        cmd.extend(['-i', overlay])
        
        # الأبعاد
        w, h = ("1280", "720") if quality == 'custom' else ("1920", "1080")
        bitrate = "3000k" if quality == 'custom' else "6000k"
        bufsize = str(int(bitrate[:-1]) * 2) + "k"
        
        # فلتر معقد للتحجيم ووضع الصورة
        filter_str = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1[bg];"
            f"[1:v]scale={w}:{h}[fg];"
            f"[bg][fg]overlay=0:0"
        )
        
        cmd.extend([
            '-filter_complex', filter_str,
            '-c:v', 'libx264', '-preset', 'veryfast', '-profile:v', 'main',
            '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', bufsize,
            '-pix_fmt', 'yuv420p', '-g', '60', '-r', '30'
        ])
    else:
        # بث عادي (Copy/Transcode)
        # نستخدم libx264 لضمان التوافق مع كل المنصات (Copy قد يفشل مع تويتر وفيسبوك اذا اختلف الكوديك)
        cmd.extend([
            '-c:v', 'libx264', '-preset', 'veryfast', 
            '-b:v', '2500k', '-maxrate', '2500k', '-bufsize', '5000k',
            '-pix_fmt', 'yuv420p', '-g', '60'
        ])

    # الصوت
    cmd.extend(['-c:a', 'aac', '-b:a', '128k', '-ar', '44100'])
    
    # أهم سطر: Format flv ليعمل مع RTMP
    cmd.extend(['-f', 'flv', output])
    
    return cmd

async def start_stream(sid, config):
    cmd = build_ffmpeg_cmd(config)
    print(f"🚀 START: {config['name']} -> {config['platform']}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return proc
    except Exception as e:
        print(f"❌ Error starting ffmpeg: {e}")
        return None

async def main():
    print(f"🌟 STREAM ENGINE STARTED | NODE KEY: {MY_NODE_KEY}")
    
    while True:
        # 1. جلب الداتا
        db_streams = await fetch_db_data()
        
        # تصفية البثوث الخاصة بهذا النود فقط
        my_targets = {}
        for sid, s in db_streams.items():
            if s.get('node_key') == MY_NODE_KEY:
                my_targets[sid] = s

        current_active_sids = list(running_streams.keys())

        # 2. الفحص وإدارة العمليات
        for sid in current_active_sids:
            
            # حالة 1: تم الحذف أو تغيير النود أو الإيقاف
            should_stop = False
            if sid not in my_targets:
                should_stop = True # حذف
            elif my_targets[sid]['status'] != 'on':
                should_stop = True # ايقاف يدوي
            elif my_targets[sid]['hash'] != running_streams[sid]['hash']:
                 # حالة 2: الهاش تغير!! (تعديل مباشر في اللوجو او الرابط)
                 # نقوم بالإيقاف هنا ليعاد التشغيل في الخطوة التالية فوراً
                 print(f"🔄 DETECTED CHANGE FOR: {running_streams[sid]['name']}")
                 should_stop = True 
            
            if should_stop:
                print(f"🛑 STOPPING: {sid}")
                try:
                    running_streams[sid]['process'].kill()
                    await running_streams[sid]['process'].wait()
                except: pass
                del running_streams[sid]

        # 3. التشغيل الجديد أو إعادة التشغيل بعد التعديل
        for sid, conf in my_targets.items():
            if conf['status'] == 'on':
                if sid not in running_streams:
                    # بدء جديد
                    proc = await start_stream(sid, conf)
                    if proc:
                        running_streams[sid] = {
                            'process': proc,
                            'hash': conf.get('hash', ''), # حفظ الهاش الحالي
                            'name': conf['name']
                        }
                else:
                    # فحص صحة العملية
                    proc = running_streams[sid]['process']
                    if proc.returncode is not None:
                        # العملية ماتت فجأة، اعادة تشغيل
                        print(f"⚠️ CRASH DETECTED: {conf['name']} -> Restarting...")
                        del running_streams[sid]
                        # سيتم اعادة تشغيلها في الدورة القادمة (بعد ثوان)
                        
        await asyncio.sleep(4) # انتظار 4 ثواني

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
