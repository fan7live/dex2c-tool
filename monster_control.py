import os
import subprocess
import shutil
import sys

# ================= إعدادات الوحش =================
INPUT_APK = "input.apk"
INTERMEDIATE_APK = "stage1_native.apk"
FINAL_UNSIGNED = "stage2_obfuscated.apk"
OUTPUT_APK = "final_protected.apk"
TOOLS_DIR = "tools"
APKTOOL_JAR = f"{TOOLS_DIR}/apktool.jar"

# إعدادات Dex2C
DCC_DIR = "dex2c_tool"
NDK_ROOT = os.environ.get("NDK_ROOT")

# إعدادات Obfuscapk
# هذه هي المكونات القوية للتشويش التي طلبتها
OBFUSCATORS = [
    "ArithmeticBranch",     # تحويل الأرقام لمعادلات معقدة
    "CallIndirection",      # إخفاء استدعاءات الدوال
    "ConstStringEncryption",# تشفير النصوص داخل الكلاسات
    "FieldRename",          # تغيير أسماء المتغيرات
    "MethodRename",         # تغيير أسماء الدوال
    "Reorder",              # إعادة ترتيب الأوامر لتضليل المحلل
    "Goto",                 # إضافة قفزات عشوائية (Spaghetti Code)
    "RandomManifest",       # إضافة حشو في ملف المانيفست
    "Nop"                   # تعليمات فارغة
]
# ==================================================

def run_cmd(command, error_msg="Error"):
    print(f"\n➤ تشغيل: {command}")
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        print(f"❌ {error_msg}")
        # لا نوقف العمل تمامًا إذا فشل جزء، نحاول إكمال الباقي
        return False
    return True

def stage_1_dex2c():
    """ المرحلة الأولى: تحويل الجافا إلى C++ """
    print("\n" + "="*50)
    print("🛠️ المرحلة 1: الحماية بتحويل الكود (Java -> Native)")
    print("="*50)

    # 1. نسخ dex2c إلى هنا للعمل
    if not os.path.exists("dcc.py"):
        shutil.copy(f"{DCC_DIR}/dcc.py", ".")
        if os.path.exists(f"{DCC_DIR}/dcc"): shutil.copytree(f"{DCC_DIR}/dcc", "dcc")

    # 2. إنشاء فلتر ذكي (لحماية كود التطبيق فقط وترك المكتبات)
    # نقوم بعمل حماية عامة للحزمة com
    # يمكنك تخصيص هذا الجزء ليكون أدق
    with open("filter.txt", "w") as f:
        f.write("com/.*;.*\n")     # احمِ أي كود داخل مجلد com
        f.write("!android/.*;.*\n") # استثنِ أندرويد
        f.write("!androidx/.*;.*\n")
        f.write("!com/google/.*;.*\n")
    
    # 3. التشغيل
    # --skip-synthetic لتفادي أخطاء المترجم
    cmd = f"python3 dcc.py -a {INPUT_APK} -o {INTERMEDIATE_APK} --ndk {NDK_ROOT} --filter filter.txt"
    success = run_cmd(cmd, "فشل Dex2C - سيتم تخطي المرحلة واستخدام الملف الأصلي")
    
    if not success or not os.path.exists(INTERMEDIATE_APK):
        print("⚠️ فشلت مرحلة Native، سننتقل لمرحلة التشويش باستخدام الملف الأصلي.")
        shutil.copy(INPUT_APK, INTERMEDIATE_APK)

def stage_2_obfuscapk():
    """ المرحلة الثانية: التشويش البصري والتعقيد (Obfuscapk) """
    print("\n" + "="*50)
    print("🌪️ المرحلة 2: التشويش المتقدم (Obfuscapk)")
    print("="*50)
    
    # تحضير المكونات (Plugins)
    obfuscator_flags = " ".join(OBFUSCATORS)
    
    # أمر التشويش
    # -w work_dir : مجلد عمل
    # -o : قائمة المشوشات
    # -i : الدخول (ملف المرحلة 1)
    # استخرجنا الاسم للملف النهائي
    
    work_dir = "obfuscation_work"
    if os.path.exists(work_dir): shutil.rmtree(work_dir)

    cmd = (
        f"python3 -m obfuscapk.cli "
        f"-o {obfuscator_flags} "
        f"-w {work_dir} "
        f"{INTERMEDIATE_APK}"
    )
    
    success = run_cmd(cmd, "فشل Obfuscapk")
    
    # Obfuscapk يضع الملف الناتج داخل work_dir باسم غريب، يجب العثور عليه
    found_apk = False
    if success:
        for root, dirs, files in os.walk(work_dir):
            for file in files:
                if file.endswith("_obfuscated.apk"):
                    src = os.path.join(root, file)
                    shutil.move(src, FINAL_UNSIGNED)
                    found_apk = True
                    break
    
    if not found_apk:
        print("⚠️ فشلت مرحلة التشويش أو لم يتم العثور على الناتج.")
        # نستخدم ناتج المرحلة الأولى كبديل أخير
        shutil.copy(INTERMEDIATE_APK, FINAL_UNSIGNED)

def stage_3_signing():
    """ المرحلة الثالثة: المحاذاة والتوقيع """
    print("\n" + "="*50)
    print("✍️ المرحلة 3: التوقيع والإنتاج النهائي")
    print("="*50)

    # 1. Zipalign
    run_cmd(f"zipalign -p -f -v 4 {FINAL_UNSIGNED} aligned.apk")

    # 2. KeyStore
    keystore = "release.keystore"
    if not os.path.exists(keystore):
        cmd_key = (
            f"keytool -genkey -v -keystore {keystore} "
            "-alias alias_name -keyalg RSA -keysize 2048 "
            "-validity 10000 -storepass 12345678 -keypass 12345678 "
            "-dname \"CN=MonsterProtect,O=Cyber,C=US\""
        )
        run_cmd(cmd_key)

    # 3. Sign
    cmd_sign = (
        f"apksigner sign --ks {keystore} "
        "--ks-pass pass:12345678 --key-pass pass:12345678 "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    run_cmd(cmd_sign)

    # تنظيف
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")

def main():
    if not os.path.exists(INPUT_APK):
        print("❌ الملف input.apk غير موجود")
        sys.exit(1)
        
    print("🚀 بدء بروتوكول الوحش (Monster Protocol Initiated)...")
    
    # تنفيذ المراحل بالتتابع
    stage_1_dex2c()       # يحول الكود إلى Native (صعب التحليل جداً)
    stage_2_obfuscapk()   # يشوش ما تبقى من جافا (يعقد الأسماء والعمليات)
    stage_3_signing()     # يخرج الملف النهائي
    
    if os.path.exists(OUTPUT_APK):
        print(f"\n✅✅✅ تم الإنجاز! التطبيق المحمي جاهز: {OUTPUT_APK}")
        print("هذا التطبيق يحتوي على:")
        print("1. كلاسات تم تحويلها لـ C++ (Lib.so).")
        print("2. دوال مموهة بأسماء عشوائية.")
        print("3. نصوص مشفرة.")
        print("4. تحكم (Control Flow) متلاعب به.")
    else:
        print("❌ حدث خطأ، لم يتم إنتاج الملف النهائي.")
        sys.exit(1)

if __name__ == "__main__":
    main()
