import os
import subprocess
import shutil
import sys
import glob

# ================= إعدادات الوحش =================
INPUT_APK = "input.apk"
INTERMEDIATE_APK = "stage1_native.apk"
FINAL_UNSIGNED = "stage2_obfuscated.apk"
OUTPUT_APK = "final_protected.apk"
TOOLS_DIR = "tools"
# Dex2C & NDK
DCC_DIR = "dex2c_tool"
NDK_ROOT = os.environ.get("NDK_ROOT")
# ==================================================

def run_cmd(command, error_msg="Error"):
    print(f"\n➤ تشغيل: {command}")
    try:
        subprocess.check_call(command, shell=True)
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {error_msg}")
        return False

def stage_1_dex2c():
    """ المرحلة 1: تحويل الجافا إلى C++ """
    print("\n" + "="*40)
    print("🛠️ Stage 1: Native Transformation (Dex2C)")
    print("="*40)

    if not os.path.exists("dcc.py"):
        if os.path.exists(f"{DCC_DIR}/dcc.py"):
            shutil.copy(f"{DCC_DIR}/dcc.py", ".")
            if os.path.exists(f"{DCC_DIR}/dcc"): shutil.copytree(f"{DCC_DIR}/dcc", "dcc", dirs_exist_ok=True)

    # إنشاء فلتر ذكي يحمي حزمة التطبيق ويترك الأندرويد
    with open("filter.txt", "w") as f:
        # يمكنك هنا تحديد الحزمة الخاصة بك بدقة للحصول على أفضل نتيجة
        # مثال: com/example/app/.*
        f.write("com/.*;.*\n")     
        f.write("!android/.*;.*\n") 
        f.write("!androidx/.*;.*\n")
        f.write("!com/google/.*;.*\n")
    
    # استخدام NDK لتجميع المكتبات
    cmd = f"python3 dcc.py -a {INPUT_APK} -o {INTERMEDIATE_APK} --ndk {NDK_ROOT} --filter filter.txt --skip-synthetic"
    
    if run_cmd(cmd, "Native protection skipped/failed") and os.path.exists(INTERMEDIATE_APK):
        print("✅ Native libraries generated successfully.")
    else:
        print("⚠️ Falling back to original APK for obfuscation.")
        shutil.copy(INPUT_APK, INTERMEDIATE_APK)

def stage_2_obfuscapk():
    """ المرحلة 2: التشفير المعقد Obfuscapk """
    print("\n" + "="*40)
    print("🌪️ Stage 2: Advanced Obfuscation")
    print("="*40)
    
    # اختيار المكونات: حذفنا Reorder/Goto لأنها أحيانًا تسبب أخطاء VerifyError في التطبيقات الكبيرة
    # لكن أبقينا على الأهم: التشفير والتمويه
    modules = "ArithmeticBranch CallIndirection ConstStringEncryption FieldRename MethodRename RandomManifest Nop"
    
    work_dir = "obfuscation_work"
    if os.path.exists(work_dir): shutil.rmtree(work_dir)

    # Obfuscapk يعتمد على الأمر 'apktool' الذي قمنا بإعداده في الـ workflow
    cmd = (
        f"obfuscapk " # الآن يعمل كأمر مباشر بعد التثبيت
        f"-o {modules} "
        f"-w {work_dir} "
        f"{INTERMEDIATE_APK}"
    )
    
    if run_cmd(cmd, "Obfuscation failed"):
        # البحث عن الناتج
        found = False
        for f in glob.glob(f"{work_dir}/*_obfuscated.apk"):
            shutil.move(f, FINAL_UNSIGNED)
            found = True
            break
        
        if not found:
            print("⚠️ Obfuscapk ran but produced no file.")
            shutil.copy(INTERMEDIATE_APK, FINAL_UNSIGNED)
    else:
        shutil.copy(INTERMEDIATE_APK, FINAL_UNSIGNED)

def stage_3_signing():
    """ المرحلة 3: التوقيع """
    print("\n" + "="*40)
    print("✍️ Stage 3: Signing")
    print("="*40)

    # تحسين الذاكرة
    run_cmd(f"zipalign -p -f -v 4 {FINAL_UNSIGNED} aligned.apk", "Zipalign failed")

    # مفتاح توقيع
    if not os.path.exists("release.keystore"):
        cmd_key = 'keytool -genkey -v -keystore release.keystore -alias beast -keyalg RSA -keysize 2048 -validity 10000 -storepass password123 -keypass password123 -dname "CN=Beast,O=Protector,C=US"'
        run_cmd(cmd_key)

    # توقيع
    cmd_sign = (
        f"apksigner sign --ks release.keystore "
        "--ks-pass pass:password123 --key-pass pass:password123 "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    
    run_cmd(cmd_sign, "Signing failed")
    
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")

def main():
    print("🚀 Initiating MONSTER PROTOCOL...")
    stage_1_dex2c()
    stage_2_obfuscapk()
    stage_3_signing()
    
    if os.path.exists(OUTPUT_APK):
        print(f"\n🎉 SUCCESS: {OUTPUT_APK}")
    else:
        print("\n❌ CRITICAL FAILURE.")
        sys.exit(1)

if __name__ == "__main__":
    main()
