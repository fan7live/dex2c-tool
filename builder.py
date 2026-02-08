import os
import shutil
import subprocess
import sys
import glob
import random
import string

# ================= إعدادات =================
INPUT_APK = "input.apk"
OUTPUT_APK = "protected.apk"
TEMP_DIR = "apk_temp"
TOOLS_DIR = "tools"
APKTOOL_PATH = os.path.join(TOOLS_DIR, "apktool.jar")
KEYSTORE_PATH = os.path.join(TOOLS_DIR, "signer.keystore")
# ==========================================

def run_command(command):
    try:
        print(f"[*] تشغيل: {command}")
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        print(f"❌ خطأ فادح أثناء تنفيذ: {command}")
        sys.exit(1)

def protect_smali(file_path):
    """ إخفاء معلومات التصحيح وحقن كود وهمي """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        is_class = False

        for line in lines:
            stripped = line.strip()
            
            # 1. حذف معلومات المبرمج (Debugging Info)
            if stripped.startswith(('.line', '.local', '.source', '.param')):
                continue

            if stripped.startswith('.class'):
                is_class = True
            
            new_lines.append(line)

        # 2. حقن دالة وهمية في النهاية لتغيير بصمة الملف
        if is_class and len(new_lines) > 2:
            junk_name = ''.join(random.choices(string.ascii_letters, k=8))
            junk_method = f"""
.method private static {junk_name}()V
    .locals 2
    const/4 v0, 0x1
    const/4 v1, 0x2
    add-int/2addr v0, v1
    return-void
.end method
"""
            # نبحث عن السطر قبل الأخير (.end class) ونحقن قبله
            for i in range(len(new_lines)-1, -1, -1):
                if new_lines[i].strip() == '.end class':
                    new_lines.insert(i, junk_method)
                    break
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("".join(new_lines))

    except Exception as e:
        print(f"⚠️ تجاوز ملف بسبب خطأ: {file_path} -> {e}")

def main():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        
    print(">>> [1/5] جاري التفكيك (Decompile)...")
    run_command(f"java -jar {APKTOOL_PATH} d {INPUT_APK} -o {TEMP_DIR} -f")

    print(">>> [2/5] جاري الحماية (Protecting Smali)...")
    smali_files = glob.glob(f"{TEMP_DIR}/**/*.smali", recursive=True)
    
    for smali in smali_files:
        # لا تحمِ ملفات النظام لكي لا ينهار التطبيق
        if "androidx" in smali or "android/support" in smali or "google" in smali:
            continue
        protect_smali(smali)

    print(">>> [3/5] إعادة البناء (Build)...")
    run_command(f"java -jar {APKTOOL_PATH} b {TEMP_DIR} -o unaligned.apk")

    print(">>> [4/5] تحسين (Zipalign)...")
    run_command("zipalign -p -f -v 4 unaligned.apk aligned.apk")

    print(">>> [5/5] التوقيع (Sign)...")
    if not os.path.exists(KEYSTORE_PATH):
        cmd = f'keytool -genkey -v -keystore {KEYSTORE_PATH} -alias test -keyalg RSA -keysize 2048 -validity 10000 -storepass 123456 -keypass 123456 -dname "CN=Test,O=Test,C=US"'
        run_command(cmd)

    run_command(f"
