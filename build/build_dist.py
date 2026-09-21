"""
build_dist.py - One-step build and packaging script for Solaron Dashboard.
Compiles the application into a standalone Windows directory (dist/Solaron)
with PyInstaller, bundles Playwright Chromium, copies templates/assets/contacts,
and creates a ready-to-distribute ZIP file for Google Drive sharing.
"""

import os
import shutil
import subprocess
import sys
import zipfile


def find_playwright_browsers():
    """Find installed Playwright chromium, headless shell, and support browser directories."""
    user_profile = os.environ.get("USERPROFILE", "")
    ms_playwright = os.path.join(user_profile, "AppData", "Local", "ms-playwright")
    results = []
    if os.path.exists(ms_playwright):
        for item in os.listdir(ms_playwright):
            if item.startswith("chromium") or item.startswith("ffmpeg") or item.startswith("winldd"):
                candidate = os.path.join(ms_playwright, item)
                if os.path.isdir(candidate):
                    results.append(candidate)
    return results


def run_pyinstaller():
    """Run PyInstaller to package launcher.py."""
    print("=" * 60)
    print("[1/3] Running PyInstaller Build...")
    print("=" * 60)

    build_script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(build_script_dir)
    dist_dir = os.path.join(base_dir, "dist")
    pyinstaller_workpath = os.path.join(base_dir, ".pyinstaller_cache")

    # Clean old build/dist
    if os.path.exists(dist_dir):
        print("Cleaning previous dist folder...")
        shutil.rmtree(dist_dir, ignore_errors=True)
    if os.path.exists(pyinstaller_workpath):
        print("Cleaning previous pyinstaller cache...")
        shutil.rmtree(pyinstaller_workpath, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=Solaron",
        f"--workpath={pyinstaller_workpath}",
        f"--specpath={pyinstaller_workpath}",
        f"--distpath={dist_dir}",
        f"--paths={base_dir}",
        f"--paths={build_script_dir}",
        # Add assets and data
        f"--add-data={os.path.join(base_dir, 'templates')};templates",
        f"--add-data={os.path.join(base_dir, 'static')};static",
        f"--add-data={os.path.join(base_dir, 'data', 'solaron.db')};data",
        f"--add-data={os.path.join(base_dir, 'data', 'contacts.csv')};data",
        f"--add-data={os.path.join(base_dir, 'data', 'Leads.csv')};data",
        f"--add-data={os.path.join(base_dir, 'data', 'plants_with_contacts.csv')};data",
        "--upx-exclude=vcruntime140.dll",
        "--upx-exclude=python3.dll",
        # Hidden imports for dynamic modules & web server
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=playwright",
        "--hidden-import=playwright.sync_api",
        "--hidden-import=pywhatkit",
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=openpyxl.cell._writer",
        "--hidden-import=jinja2",
        "--hidden-import=fastapi",
        "--hidden-import=pydantic",
        "--hidden-import=pydantic_settings",
        "--hidden-import=growattServer",
        "--hidden-import=click",
        # SQLAlchemy
        "--hidden-import=sqlalchemy",
        "--hidden-import=sqlalchemy.sql.default_comparator",
        "--hidden-import=sqlalchemy.ext.declarative",
        # CRM package
        "--hidden-import=crm",
        "--hidden-import=crm.db",
        "--hidden-import=crm.models",
        "--hidden-import=crm.queue_manager",
        "--hidden-import=crm.generator",
        "--hidden-import=crm.sender",
        "--hidden-import=crm.templates",
        # Services
        "--hidden-import=services.scheduler",
        "--hidden-import=services.classifier",
        "--hidden-import=services.contacts",
        "--hidden-import=services.deviation",
        "--hidden-import=services.fetcher_orchestrator",
        "--hidden-import=services.history",
        "--hidden-import=services.report",
        "--hidden-import=services.send_tracker",
        "--hidden-import=services.excel",
        "--hidden-import=services.excel.parser",
        "--hidden-import=services.excel.updater",
        "--hidden-import=services.excel.writer",
        "--hidden-import=services.growatt",
        "--hidden-import=services.growatt.fetcher",
        "--hidden-import=services.growatt.cache",
        "--hidden-import=services.isolarcloud",
        "--hidden-import=services.isolarcloud.fetcher",
        "--hidden-import=services.isolarcloud.cache",
        "--hidden-import=services.suryalog",
        "--hidden-import=services.suryalog.fetcher",
        "--hidden-import=services.suryalog.cache",
        "--hidden-import=services.messaging",
        "--hidden-import=services.messaging.whatsapp",
        "--hidden-import=services.messaging.generator",
        # Routes
        "--hidden-import=routes.crm",
        "--hidden-import=routes.diagnostics",
        "--hidden-import=routes.contacts",
        "--hidden-import=routes.fetch",
        "--hidden-import=routes.plants",
        "--hidden-import=routes.report",
        "--hidden-import=routes.send",
        "--hidden-import=routes.upload",
        # Exclude unrelated heavy global packages to prevent hook failures and bloat

        "--exclude-module=tensorflow",
        "--exclude-module=torch",
        "--exclude-module=torchvision",
        "--exclude-module=torchaudio",
        "--exclude-module=IPython",
        "--exclude-module=ipykernel",
        "--exclude-module=jupyter",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=sklearn",
        "--exclude-module=transformers",
        "--exclude-module=streamlit",
        "--exclude-module=botocore",
        "--exclude-module=boto3",
        "--exclude-module=sagemaker_studio",
        "--exclude-module=xgboost",
        "--exclude-module=shap",
        "--exclude-module=numba",
        "--exclude-module=llvmlite",
        os.path.join(build_script_dir, "launcher.py"),
    ]

    print(f"Executing PyInstaller command...")
    result = subprocess.run(cmd, cwd=base_dir)
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller build failed with exit code {result.returncode}")
        return False

    print("[SUCCESS] PyInstaller build finished successfully!")
    return True


def copy_bundled_assets():
    """Copy Chromium, docs, and default data to dist/Solaron."""
    print("=" * 60)
    print("[2/3] Bundling Playwright Chromium and Resources...")
    print("=" * 60)

    build_script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(build_script_dir)
    dist_solaron = os.path.join(base_dir, "dist", "Solaron")

    if not os.path.exists(dist_solaron):
        print(f"[ERROR] Target directory {dist_solaron} not found!")
        return False

    # 1. Copy Playwright Chromium and Headless Shell packages
    browser_dirs = find_playwright_browsers()
    if browser_dirs:
        for b_src in browser_dirs:
            folder_name = os.path.basename(b_src)
            target_browser_dir = os.path.join(dist_solaron, "playwright-browsers", folder_name)
            print(f"Copying Playwright browser component {folder_name} -> {target_browser_dir}...")
            os.makedirs(os.path.dirname(target_browser_dir), exist_ok=True)
            shutil.copytree(b_src, target_browser_dir, dirs_exist_ok=True)
        print("[SUCCESS] Bundled all Playwright browser packages successfully!")
    else:
        print("[WARNING] Could not locate Playwright browsers in default location.")

    # 2. Copy README.md
    readme_src = os.path.join(base_dir, "README.md")
    if os.path.exists(readme_src):
        shutil.copy2(readme_src, os.path.join(dist_solaron, "README.md"))
        print("[SUCCESS] Copied README.md")

    # 3. Create initial data folder and files in dist
    data_dest = os.path.join(dist_solaron, "data")
    os.makedirs(data_dest, exist_ok=True)
    
    # Run DB Migration if DB doesn't exist
    db_path = os.path.join(base_dir, "data", "solaron.db")
    if not os.path.exists(db_path):
        print("solaron.db not found. Running data migration script...")
        subprocess.run([sys.executable, os.path.join(base_dir, "tools", "migrate_to_db.py")], cwd=base_dir)

    if os.path.exists(db_path):
        shutil.copy2(db_path, os.path.join(data_dest, "solaron.db"))
        print("[SUCCESS] Copied solaron.db database.")
    else:
        print("[WARNING] solaron.db could not be found or generated.")

    # 4. Copy contacts and CRM data files
    for data_file in ["contacts.csv", "Leads.csv", "plants_with_contacts.csv", "plants_without_contacts.csv"]:
        src = os.path.join(base_dir, "data", data_file)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(data_dest, data_file))
            print(f"[SUCCESS] Copied {data_file}")

    # 5. Copy pre-seeded crm_data.db
    crm_db_src = os.path.join(base_dir, "data", "crm_data.db")
    if os.path.exists(crm_db_src):
        shutil.copy2(crm_db_src, os.path.join(data_dest, "crm_data.db"))
        print("[SUCCESS] Copied crm_data.db (pre-seeded CRM)")

    # 6. Create required subdirectories in dist data folder
    for subdir in ["exports", "growatt_cache", "isolarcloud_cache", "suryalog_cache", "history"]:
        os.makedirs(os.path.join(data_dest, subdir), exist_ok=True)
    print("[SUCCESS] Created data subdirectories")

    # 7. Create uploads directory
    uploads_dest = os.path.join(dist_solaron, "uploads")
    os.makedirs(uploads_dest, exist_ok=True)
    print("[SUCCESS] Created uploads directory")

    # 8. Copy .env if available
    env_src = os.path.join(base_dir, ".env")
    if not os.path.exists(env_src):
        alt_env = os.path.join(base_dir, "Message Dashboard.env")
        if os.path.exists(alt_env):
            env_src = alt_env
    if os.path.exists(env_src):
        shutil.copy2(env_src, os.path.join(dist_solaron, ".env"))
        print("[SUCCESS] Copied configured .env")

    return True


def create_zip_archive():
    """Create Solaron_Dashboard_Windows.zip in dist/."""
    print("=" * 60)
    print("[3/3] Creating Solaron_Dashboard_Windows.zip...")
    print("=" * 60)

    build_script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(build_script_dir)
    dist_dir = os.path.join(base_dir, "dist")
    source_dir = os.path.join(dist_dir, "Solaron")
    zip_path = os.path.join(dist_dir, "Solaron_Dashboard_Windows.zip")

    if not os.path.exists(source_dir):
        print(f"[ERROR] Source directory {source_dir} not found!")
        return False

    print(f"Compressing {source_dir} -> {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(source_dir))
                zipf.write(file_path, arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[SUCCESS] Distribution ZIP generated: {zip_path} ({size_mb:.1f} MB)")
    return True


def main():
    print("=" * 60)
    print("Solaron Dashboard Windows App Packaging")
    print("=" * 60)

    if not run_pyinstaller():
        sys.exit(1)

    if not copy_bundled_assets():
        sys.exit(1)

    if not create_zip_archive():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("BUILD & PACKAGING COMPLETE!")
    print("Ready-to-run app directory:")
    print("   dist/Solaron/Solaron.exe")
    print("Shareable ZIP file for Google Drive:")
    print("   dist/Solaron_Dashboard_Windows.zip")
    print("=" * 60)


if __name__ == "__main__":
    main()
