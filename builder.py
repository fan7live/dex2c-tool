import os
import shutil
import subprocess
import sys
import glob
import random
import string

# ================= إعدادات المسارات =================
INPUT_APK = "input.apk"
OUTPUT_APK = "protected.apk"
TEMP_DIR = "apk_temp"
TOOLS_DIR = "tools"
APKTOOL_JAR = os.path.join(TOOLS_DIR, "apktool.jar")
KEYSTORE_PATH = os.path.join(TOOLS_DIR, "signer.keystore")
# ==================================================

def run_command(command):
    """ دالة لتنفيذ الأوامر مع طباعة الأخطاء بوضوح """
    try:
        print(f"[*] تنفيذ: {command}")
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ خطأ فادح: فشل الأمر برمز خروج {e.returncode}")
        sys.exit(1)

def protect_smali(file_path):
    """ دالة الحماية: تنظيف الكود وحقن التشويش """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        new_lines = []
        is_class = False
        class_lines_count = len(lines)

        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # --- إصلاح الخطأ السابق هنا ---
            # 1. حذف معلومات المطور (Debug Info) بحذر
            
            # حذف أرقام الأسطر
            if stripped.startswith('.line '): 
                continue
                
            # حذف اسم الملف الأصلي
            if stripped.startswith('.source '): 
                continue
                
            # حذف أسماء المتغيرات (Variable Names) 
            # لكن !!! ممنوع حذف .locals (بصيغة الجمع) لأنها تحدد حجم الذاكرة
            if stripped.startswith('.local ') and not stripped.startswith('.locals'): 
                continue
            
            # -------------------------------
            
            if stripped.startswith('.class'):
                is_class = True
            
            new_lines.append(line)

        # 2. حقن دالة وهمية في النهاية (Junk Code)
        # فقط إذا كان الملف كبيراً بما يكفي (تجنب الملفات الصغيرة جداً أو الواجهات interfaces)
        if is_class and class_lines_count > 20:
            # اسم عشوائي للدالة لمنع التكرار
            junk_name = "z" + ''.join(random.choices(string.ascii_lowercase, k=6))
            
            # كود دالة فارغة تماماً وآمنة (Safe Void Method)
            junk_method = f"\n.method public static {junk_name}()V\n"
            junk_method += "    .locals 0\n"
            junk_method += "    return-void\n"
            junk_method += ".end method\n"

            # البحث عن آخر سطر (.end class) للإضافة قبله
            injected = False
            for i in range(len(new_lines)-1, 0, -1):
                if new_lines[i].strip().startswith('.end class'):
                    new_lines.insert(i, junk_method)
                    injected = True
                    break
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("".join(new_lines))

    except Exception as e:
        print(f"⚠️ تجاوز ملف بسبب خطأ عرضي: {file_path}")

def main():
    print(">>> بدء عملية الحماية (Fixed Mode) ...")

    # تنظيف مسبق
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    
    # 1. تفكيك التطبيق
    print(">>> [1/5] جاري تفكيك APK...")
    # استخدام -r لمنع تفكيك الموارد (resources) أحياناً يسرع ويقلل الأخطاء، لكن سنتركه لضمان التوافق
    run_command(f"java -jar {APKTOOL_JAR} d {INPUT_APK} -o {TEMP_DIR} -f")

    # 2. حماية الكود
    print(">>> [2/5] جاري تشفير وحماية Smali...")
    # البحث عن كل ملفات smali في كل المجلدات
    smali_files = glob.glob(f"{TEMP_DIR}/**/*.smali", recursive=True)
    
    count_protected = 0
    count_skipped = 0

    for smali in smali_files:
        # التطبيع مع مسار الملف لتجنب مشاكل ويندوز/لينكس
        path_str = smali.replace("\\", "/")
        
        # --- استثناءات مهمة جداً (قائمة الحظر) ---
        # لا نلمس ملفات النظام أو المكتبات المشهورة لأن تعديلها يكسر التطبيق فوراً
        if "android/" in path_str or \
           "androidx/" in path_str or \
           "com/google/" in path_str or \
           "kotlin/" in path_str or \
           "R$" in path_str or \
           "BuildConfig" in path_str:
            count_skipped += 1
            continue
            
        protect_smali(smali)
        count_protected += 1

    print(f"[*] تم الانتهاء: حماية {count_protected} ملف | تجاوز {count_skipped} ملف نظام.")

    # 3. إعادة البناء
    print(">>> [3/5] إعادة بناء APK...")
    run_command(f"java -jar {APKTOOL_JAR} b {TEMP_DIR} -o unaligned.apk")

    # 4. محاذاة
    print(">>> [4/5] تحسين (Zipalign)...")
    run_command("zipalign -p -f -v 4 unaligned.apk aligned.apk")

    # 5. التوقيع
    print(">>> [5/5] توقيع التطبيق...")
    if not os.path.exists(KEYSTORE_PATH):
        cmd_keygen = (
            f"keytool -genkey -v -keystore {KEYSTORE_PATH} "
            "-alias androiddebugkey -keyalg RSA -keysize 2048 "
            "-validity 10000 -storepass android -keypass android "
            "-dname \"CN=Android Debug,O=Android,C=US\""
        )
        run_command(cmd_keygen)

    cmd_sign = (
        f"apksigner sign --ks {KEYSTORE_PATH} "
        "--ks-pass pass:android --key-pass pass:android "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    run_command(cmd_sign)

    # تنظيف
    if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")
    if os.path.exists("unaligned.apk"): os.remove("unaligned.apk")

    print(f"\n🎉 تم بنجاح! حمل تطبيقك من: {OUTPUT_APK}")

if __name__ == "__main__":
    main()
