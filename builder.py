import os
import re
import shutil
import subprocess
import sys
import glob
import random
import string

# إعدادات الحماية
PROTECTION_LEVEL_STRIP_DEBUG = True  # حذف معلومات التنقيح
PROTECTION_LEVEL_JUNK_CODE = True    # إضافة كود وهمي
INPUT_APK = "input.apk"
OUTPUT_APK = "protected.apk"
TEMP_DIR = "apk_temp"

def run_command(command):
    """تشغيل الأوامر النظامية والتأكد من نجاحها"""
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ خطأ أثناء تنفيذ: {command}")
        sys.exit(1)

def generate_junk_method():
    """توليد كود smali لدالة وهمية عشوائية لا تفعل شيئًا خطيرًا"""
    method_name = ''.join(random.choices(string.ascii_lowercase, k=10))
    # هذه دالة بسيطة تحسب عمليات حسابية ولا تستخدم ناتجها
    # هذا يربك المحلل ويغير هيكل الملف
    smali_code = f"""
.method private {method_name}()V
    .locals 2
    const/4 v0, 0x1
    const/4 v1, 0x2
    add-int v0, v0, v1
    return-void
.end method
"""
    return smali_code

def protect_smali_file(file_path):
    """تطبيق الحماية على ملف Smali واحد"""
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    class_name_found = False
    
    for line in lines:
        stripped_line = line.strip()
        
        # 1. الحماية: حذف معلومات التصحيح (Debug Info)
        # نحذف الأسطر التي تبدأ بـ .line أو .local أو .source
        if PROTECTION_LEVEL_STRIP_DEBUG:
            if stripped_line.startswith(".line") or \
               stripped_line.startswith(".local") or \
               stripped_line.startswith(".source") or \
               stripped_line.startswith(".param"):
                continue

        # تسجيل مكان بداية الكلاس لحقن الكود الوهمي لاحقًا
        if stripped_line.startswith(".class"):
            class_name_found = True

        new_lines.append(line)

        # 2. الحماية: حقن دالة وهمية في نهاية الملف (قبل .end descriptor المباشر لا يجوز، الأفضل بعد بداية الكلاس مباشرة أو قبل النهاية)
        # للتسهيل والاستقرار، سنضيفها قبل نهاية الملف
    
    # تحضير المحتوى للكتابة
    final_content = "".join(new_lines)
    
    # حقن Junk Method قبل آخر سطر (الذي يكون عادة .end descriptor محذوف أو موجود)
    # للأسلوب الأكثر أمانًا، نبحث عن آخر سطر ونضع قبله
    if PROTECTION_LEVEL_JUNK_CODE and class_name_found:
        # البحث عن .end class لغلق الملف
        if final_content.strip().endswith(".end class"):
             junk = generate_junk_method()
             final_content = final_content.replace(".end class", f"{junk}\n.end class")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)

def main():
    print("🚀 بدء نظام الحماية (حصن DEX)...")
    
    # 1. التفكيك (Decompilation)
    print("📦 جاري تفكيك APK...")
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    
    # نستخدم apktool لتفكيك الملف
    run_command(f"java -jar tools/apktool.jar d {INPUT_APK} -o {TEMP_DIR} -f")

    # 2. تطبيق الحماية (Applying Protection)
    print("🛡️ جاري تشفير وحماية ملفات DEX/Smali...")
    smali_files = glob.glob(f"{TEMP_DIR}/smali*/**/*.smali", recursive=True)
    
    count = 0
    for smali_file in smali_files:
        # نستبعد مكتبات النظام الأساسية لتسريع العملية وتجنب الأخطاء
        if "android/support" in smali_file or "androidx" in smali_file:
            continue
            
        protect_smali_file(smali_file)
        count += 1
    
    print(f"✅ تمت حماية {count} ملف بنجاح.")

    # 3. إعادة البناء (Rebuilding)
    print("🔨 جاري إعادة بناء APK...")
    run_command(f"java -jar tools/apktool.jar b {TEMP_DIR} -o unaligned.apk")

    # 4. التوقيع والتحسين (Align & Sign)
    # Zipalign مهم لاستقرار الرام في أندرويد
    print("⚖️ جاري تحسين المحاذاة (Zipalign)...")
    run_command("zipalign -p -f -v 4 unaligned.apk aligned.apk")

    # التوقيع بمفتاح تصحيح مؤقت (Debug Key) بما أننا في بيئة تلقائية
    print("✍️ جاري توقيع التطبيق...")
    # إنشاء مفتاح مؤقت إذا لم يوجد
    if not os.path.exists("tools/signer.keystore"):
        run_command('keytool -genkey -v -keystore tools/signer.keystore -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -storepass android -keypass android -dname "CN=Android Debug,O=Android,C=US"')

    run_command(f"apksigner sign --ks tools/signer.keystore --ks-pass pass:android --key-pass pass:android --out {OUTPUT_APK} aligned.apk")

    # تنظيف
    if os.path.exists("unaligned.apk"): os.remove("unaligned.apk")
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")
    if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)

    print(f"🎉 تم الانتهاء! الملف المحمي جاهز: {OUTPUT_APK}")

if __name__ == "__main__":
    main()
