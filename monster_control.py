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
# Dex2C setup
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
    """ المرحلة 1: الحماية بتحويل الجافا لـ Native """
    print("\n" + "="*40)
    print("🛠️ Stage 1: Dex2C (Native Protection)")
    print("="*40)

    # جلب ملف dcc.py من المجلد الذي تم استنساخه
    if not os.path.exists("dcc.py"):
        if os.path.exists(f"{DCC_DIR}/dcc.py"):
            shutil.copy(f"{DCC_DIR}/dcc.py", ".")
            if os.path.exists(f"{DCC_DIR}/dcc"): 
                shutil.copytree(f"{DCC_DIR}/dcc", "dcc", dirs_exist_ok=True)

    # إنشاء ملف فلتر لتحديد الحزم
    with open("filter.txt", "w") as f:
        # هنا يتم تحديد ما يتم حمايته (تلقائيا نحمي كل حزمة com)
        f.write("com/.*;.*\n")     
        f.write("!android/.*;.*\n") 
        f.write("!androidx/.*;.*\n")
        f.write("!com/google/.*;.*\n")
    
    # تنفيذ Dex2C
    # ملاحظة: إذا فشل هذا، غالبا بسبب تعارض NDK أو عدم وجود كلاسات متوافقة
    cmd = f"python3 dcc.py -a {INPUT_APK} -o {INTERMEDIATE_APK} --ndk {NDK_ROOT} --filter filter.txt --skip-synthetic"
    
    if run_cmd(cmd, "تحذير: Dex2C لم يعمل كما يجب، سننتقل للتشفير المباشر") and os.path.exists(INTERMEDIATE_APK):
        print("✅ Dex2C نجح في تحويل الكود.")
    else:
        print("⚠️ سيتم تخطي Dex2C واستخدام APK الأصلي.")
        shutil.copy(INPUT_APK, INTERMEDIATE_APK)

def stage_2_obfuscapk():
    """ المرحلة 2: تشفير وفوضى الكود (Obfuscapk) """
    print("\n" + "="*40)
    print("🌪️ Stage 2: Obfuscapk (Logic Scrambling)")
    print("="*40)
    
    # اختيار الهجمات الدفاعية
    # ArithmeticBranch: يحول الأرقام لمعادلات
    # RandomManifest: يضيف ملفات وهمية
    # ClassRename / MethodRename: يغير الأسماء
    obfuscators = "ArithmeticBranch CallIndirection ConstStringEncryption FieldRename MethodRename RandomManifest Nop"
    
    work_dir = "obfuscation_work"
    if os.path.exists(work_dir): shutil.rmtree(work_dir)

    cmd = (
        f"obfuscapk "
        f"-o {obfuscators} "
        f"-w {work_dir} "
        f"{INTERMEDIATE_APK}"
    )
    
    success = run_cmd(cmd, "Obfuscapk encountered an error")
    
    # العثور على الملف الناتج
    found = False
    if success:
        for f in glob.glob(f"{work_dir}/*_obfuscated.apk"):
            shutil.move(f, FINAL_UNSIGNED)
            found = True
            break
            
    if not found:
        print("⚠️ Obfuscapk لم ينتج ملفاً، نستخدم المرحلة السابقة.")
        shutil.copy(INTERMEDIATE_APK, FINAL_UNSIGNED)

def stage_3_signing():
    """ المرحلة 3: التوقيع """
    print("\n" + "="*40)
    print("✍️ Stage 3: Signing & ZipAlign")
    print("="*40)

    # 1. ZipAlign
    run_cmd(f"zipalign -p -f -v 4 {FINAL_UNSIGNED} aligned.apk", "فشل Zipalign")

    # 2. KeyStore
    keystore = "my_key.jks"
    if not os.path.exists(keystore):
        cmd_k = 'keytool -genkey -v -keystore my_key.jks -alias secure -keyalg RSA -keysize 2048 -validity 10000 -storepass 123456 -keypass 123456 -dname "CN=Sec,O=App,C=US"'
        run_cmd(cmd_k)

    # 3. Sign
    cmd_s = (
        f"apksigner sign --ks my_key.jks "
        "--ks-pass pass:123456 --key-pass pass:123456 "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    run_cmd(cmd_s, "فشل التوقيع النهائي")

    if os.path.exists("aligned.apk"): os.remove("aligned.apk")

def main():
    print("🚀 بدء المعركة...")
    stage_1_dex2c()
    stage_2_obfuscapk()
    stage_3_signing()
    
    if os.path.exists(OUTPUT_APK):
        print(f"\n🎉 مبروك! التطبيق المحمي جاهز للتحميل: {OUTPUT_APK}")
    else:
        print("\n❌ حدث خطأ، لم يتم استخراج الملف النهائي.")
        sys.exit(1)

if __name__ == "__main__":
    main()
