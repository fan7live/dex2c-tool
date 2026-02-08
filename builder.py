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
        # استخدام shell=True لتسهيل التعامل مع المسارات
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

        for line in lines:
            stripped = line.strip()
            
            # 1. حذف معلومات المطور (Anti-Debug Info)
            # هذه المعلومات تساعد الهاكرز في فهم الكود، نحن نحذفها
            if stripped.startswith('.source') or stripped.startswith('.line') or stripped.startswith('.local'):
                continue
            
            # تحديد بداية الكلاس
            if stripped.startswith('.class'):
                is_class = True
            
            new_lines.append(line)

        # 2. حقن دالة وهمية في النهاية (Junk Code Injection)
        # هذا يجعل البصمة الرقمية (Hash) للملف تتغير تمامًا
        if is_class and len(new_lines) > 2:
            junk_name = "z" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            
            # كود دالة وهمية آمن لا يكسر التطبيق
            junk_method = f"\n.method public static {junk_name}()V\n"
            junk_method += "    .locals 1\n"
            junk_method += "    const/4 v0, 0x0\n"
            junk_method += "    return-void\n"
            junk_method += ".end method\n"

            # البحث عن مكان مناسب للحقن (قبل نهاية الكلاس مباشرة)
            injected = False
            for i in range(len(new_lines)-1, 0, -1):
                if new_lines[i].strip().startswith('.end class'):
                    new_lines.insert(i, junk_method)
                    injected = True
                    break
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("".join(new_lines))

    except Exception as e:
        print(f"⚠️ تحذير: لم تتم حماية {file_path} - السبب: {e}")

def main():
    print(">>> بدء عملية الحماية (Fortress Mode) ...")

    # 1. التنظيف الأولي
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    
    if os.path.exists("unaligned.apk"):
        os.remove("unaligned.apk")

    # 2. تفكيك التطبيق (Decompile)
    print(">>> [1/5] جاري تفكيك APK...")
    cmd_decomp = f"java -jar {APKTOOL_JAR} d {INPUT_APK} -o {TEMP_DIR} -f"
    run_command(cmd_decomp)

    # 3. تشفير وحماية ملفات Smali
    print(">>> [2/5] جاري تطبيق الحماية على الكود...")
    smali_files = glob.glob(f"{TEMP_DIR}/**/*.smali", recursive=True)
    
    for smali in smali_files:
        # تجاوز ملفات الأندرويد الأساسية لتجنب تدمير التطبيق
        if "androidx" in smali or "android/support" in smali or "kotlin" in smali:
            continue
        protect_smali(smali)

    # 4. إعادة البناء (Build)
    print(">>> [3/5] إعادة تجميع التطبيق...")
    cmd_build = f"java -jar {APKTOOL_JAR} b {TEMP_DIR} -o unaligned.apk"
    run_command(cmd_build)

    # 5. محاذاة الملف (Zipalign)
    print(">>> [4/5] تحسين الذاكرة (Zipalign)...")
    cmd_align = "zipalign -p -f -v 4 unaligned.apk aligned.apk"
    run_command(cmd_align)

    # 6. التوقيع (Signing)
    print(">>> [5/5] توقيع التطبيق المحمي...")
    
    # إنشاء مفتاح إذا لم يوجد
    if not os.path.exists(KEYSTORE_PATH):
        # تم تقسيم الأمر الطويل لمنع الأخطاء
        cmd_keygen = (
            f"keytool -genkey -v -keystore {KEYSTORE_PATH} "
            "-alias androiddebugkey -keyalg RSA -keysize 2048 "
            "-validity 10000 -storepass android -keypass android "
            "-dname \"CN=Android Debug,O=Android,C=US\""
        )
        run_command(cmd_keygen)

    # توقيع التطبيق
    # تم تقسيم الأمر هنا أيضًا لأنه كان سبب المشكلة لديك
    cmd_sign = (
        f"apksigner sign --ks {KEYSTORE_PATH} "
        "--ks-pass pass:android --key-pass pass:android "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    run_command(cmd_sign)

    # تنظيف
    print(">>> تنظيف الملفات المؤقتة...")
    if os.path.exists(TEMP_DIR): shutil.rmtree(TEMP_DIR)
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")
    if os.path.exists("unaligned.apk"): os.remove("unaligned.apk")

    print(f"\n🎉 ✅ تم الانتهاء! التطبيق المحمي موجود باسم: {OUTPUT_APK}")

if __name__ == "__main__":
    main()
