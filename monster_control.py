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

# Dex2C & NDK Configuration
DCC_DIR = "dex2c_tool"
NDK_ROOT = os.environ.get("NDK_ROOT")
# ==================================================

def run_cmd(command, error_msg="Error"):
    print(f"\n➤ تشغيل: {command}")
    try:
        # shell=True يسمح بتشغيل الأوامر المعقدة
        subprocess.check_call(command, shell=True)
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {error_msg}")
        return False

def stage_1_dex2c():
    """ المرحلة 1: تحويل الجافا إلى C++ (Dex2C) """
    print("\n" + "="*50)
    print("🛠️ Stage 1: Native Transformation (C++)")
    print("="*50)

    # 1. إحضار ملف السكربت dcc.py
    if not os.path.exists("dcc.py"):
        if os.path.exists(f"{DCC_DIR}/dcc.py"):
            shutil.copy(f"{DCC_DIR}/dcc.py", ".")
            # نسخ المجلدات المساعدة
            if os.path.exists(f"{DCC_DIR}/dcc"): 
                shutil.copytree(f"{DCC_DIR}/dcc", "dcc", dirs_exist_ok=True)
        else:
            print("⚠️ dcc.py not found in dex2c_tool dir.")

    # 2. إنشاء فلتر ذكي (لحماية الحزم المهمة فقط)
    # ملاحظة: إذا كنت تعرف اسم الباكيج الخاص بك ضعه بدل 'com/.*' ليكون أسرع وأدق
    # مثال: f.write("com/my/app/.*;.*\n")
    with open("filter.txt", "w") as f:
        f.write("com/.*;.*\n")           # احمِ الكلاسات الشائعة
        f.write("!android/.*;.*\n")      # استثناء النظام
        f.write("!androidx/.*;.*\n")
        f.write("!com/google/.*;.*\n")   # استثناء خدمات جوجل
        f.write("!kotlin/.*;.*\n")       # استثناء كوتلن لتجنب الكراش

    # 3. التشغيل
    # --skip-synthetic : مهم جداً لتجنب توقف العملية بسبب كلاسات الجافا الداخلية
    cmd = f"python3 dcc.py -a {INPUT_APK} -o {INTERMEDIATE_APK} --ndk {NDK_ROOT} --filter filter.txt --skip-synthetic"
    
    success = run_cmd(cmd, "تحذير: Dex2C واجه مشكلة (سيتم تخطي هذه المرحلة).")
    
    # التأكد من نجاح العملية
    if success and os.path.exists(INTERMEDIATE_APK):
        print("✅ تم تحويل الكود إلى Native بنجاح.")
    else:
        print("⚠️ سيتم استخدام APK الأصلي للمرحلة التالية.")
        shutil.copy(INPUT_APK, INTERMEDIATE_APK)

def stage_2_obfuscapk():
    """ المرحلة 2: التشفير المعقد (Obfuscapk) """
    print("\n" + "="*50)
    print("🌪️ Stage 2: Advanced Obfuscation & Renaming")
    print("="*50)
    
    # قائمة التشويشات النشطة (تم اختيار الأكثر استقراراً وقوة)
    # ArithmeticBranch: يجعل الأرقام معادلات
    # CallIndirection: يخفي من ينادي من
    # ConstStringEncryption: يشفر النصوص
    # MethodRename: يغير أسماء الدوال
    obfuscators = "ArithmeticBranch CallIndirection ConstStringEncryption FieldRename MethodRename RandomManifest Nop"
    
    work_dir = "obfuscation_work"
    if os.path.exists(work_dir): shutil.rmtree(work_dir)

    # تشغيل الأمر (يعتمد على apktool المثبت في النظام بالخطوة السابقة)
    cmd = (
        f"obfuscapk "
        f"-o {obfuscators} " # الموديلات المختارة
        f"-w {work_dir} "    # مجلد العمل
        f"{INTERMEDIATE_APK}" # الملف القادم من المرحلة 1
    )
    
    success = run_cmd(cmd, "فشل Obfuscapk في إتمام العملية.")
    
    # البحث عن الناتج ونقله
    found = False
    if success:
        # Obfuscapk يضيف _obfuscated للاسم، نبحث عنه
        for f in glob.glob(f"{work_dir}/*_obfuscated.apk"):
            print(f"✅ Found obfuscated file: {f}")
            shutil.move(f, FINAL_UNSIGNED)
            found = True
            break
        
    if not found:
        print("⚠️ لم يتم العثور على الملف المشوش، سنستخدم ناتج المرحلة السابقة.")
        shutil.copy(INTERMEDIATE_APK, FINAL_UNSIGNED)

def stage_3_signing():
    """ المرحلة 3: التوقيع والإخراج """
    print("\n" + "="*50)
    print("✍️ Stage 3: Zipalign & Sign")
    print("="*50)

    # 1. Zipalign (تحسين)
    run_cmd(f"zipalign -p -f -v 4 {FINAL_UNSIGNED} aligned.apk", "فشل Zipalign")

    # 2. KeyStore generation
    keystore = "secure_key.jks"
    if not os.path.exists(keystore):
        cmd_key = (
            f"keytool -genkey -v -keystore {keystore} "
            "-alias ghost -keyalg RSA -keysize 2048 "
            "-validity 10000 -storepass 12345678 -keypass 12345678 "
            "-dname \"CN=Ghost,O=Privacy,C=US\""
        )
        run_cmd(cmd_key)

    # 3. Signing
    cmd_sign = (
        f"apksigner sign --ks {keystore} "
        "--ks-pass pass:12345678 --key-pass pass:12345678 "
        f"--out {OUTPUT_APK} aligned.apk"
    )
    
    run_cmd(cmd_sign, "فشل عملية التوقيع.")
    
    # تنظيف
    if os.path.exists("aligned.apk"): os.remove("aligned.apk")

def main():
    print("🚀 بدء بروتوكول الوحش (Protection Protocol Started)...")
    
    # تنفيذ المراحل بالترتيب
    stage_1_dex2c()     # (Strong) يحول إلى C++
    stage_2_obfuscapk() # (Confusing) يغير المسميات ويشفر
    stage_3_signing()   # (Finalize) يوقع التطبيق
    
    if os.path.exists(OUTPUT_APK):
        print(f"\n🎉 تمت المهمة بنجاح! الملف جاهز: {OUTPUT_APK}")
    else:
        print("\n❌ حدث خطأ فادح: لم يتم إنشاء الملف النهائي.")
        sys.exit(1)

if __name__ == "__main__":
    main()
