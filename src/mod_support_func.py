import os
import sys
import shutil
import zipfile
import tempfile
import pathlib
import platform
import subprocess
import urllib.request
import hashlib
import base64

import streamlit as st

APP_NAME = "Balatro Mod Manager" # shown in the actual browser tab
BACKUP_DIRNAME = "_backup_BalatroArt" # store all the backups here for reverting to original art
TARGET_RELATIVE = os.path.join("Balatro_Data", "StreamingAssets")
EXE_NAME = "Balatro.exe"

# Folder that holds downloadable mod zips (commit these to your repo)
MODS_DIR = os.path.join(os.path.dirname(__file__), "mods") # mods folder for where the card art zip is with the 7-zip heirarchy

# seraching for 7z.exe to easily install the mod
SEVEN_ZIP_CANDIDATES = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "7z.exe",
]




def local_css(file_name: str) -> None:
    """ Read in the CSS file and apply it to the app """
    try:
        css_path = pathlib.Path(__file__).parent / file_name  # Uses the file's directory
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSS file {file_name} not found!")

# Traversing, Finding, Downloading, and Hashing Utilities ===================
def safe_join(root: str, relpath: str) -> str:
    ''' Safely join a root and relative path, preventing path traversal. '''
    dest = os.path.abspath(os.path.join(root, relpath))
    if not dest.startswith(os.path.abspath(root)):
        raise ValueError("Unsafe path in archive.")
    return dest

def copytree_merge(src, dst):
    ''' Copy contents of src into dst, merging with existing files. '''
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target_root = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(target_root, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(target_root, d), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(target_root, f))

def download(url: str) -> str:
    ''' Download a URL to a temp file and return its path. '''
    tmp = tempfile.mkstemp(suffix=".zip")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    return tmp

def find_7z() -> str | None:
    ''' Find 7z.exe in common locations or PATH on the computer. '''
    for p in SEVEN_ZIP_CANDIDATES:
        found = shutil.which(p) or (p if os.path.isfile(p) else None)
        if found:
            return shutil.which(p) or p
    return None

def file_sha256(path: str) -> str:
    ''' Compute SHA-256 hash of a file. (used for verifying downloads and ensuring file integrity) '''
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# Making Sure Balatro is in Steam Library ====================
def detect_steam_libraries() -> list[str]:
    ''' Detect Steam library folders on the system. '''
    paths = [] # list of detected steam library folders
    system = platform.system() # detecting the operating system
    home = str(pathlib.Path.home()) # getting the home directory
    candidates = [] # candidate steam library roots

    if system == "Windows": # finding the Steam library on windows
        candidates += [
            os.path.join(home, "AppData", "Local", "Steam"),
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
        ]
    elif system == "Darwin": # finding the Steam library on macOS (what python uses to detect the home folder))
        candidates += [os.path.join(home, "Library", "Application Support", "Steam")]
    else:
        candidates += [
            os.path.join(home, ".local", "share", "Steam"),
            os.path.join(home, ".steam", "steam"),
        ]

    for root in candidates: # reading the steam libraryfolders.vdf file to find additional steam libraries
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf") #everything is through the steamapps dir
        if os.path.isfile(vdf):
            try:
                with open(vdf, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                for line in text.splitlines():
                    line = line.strip()
                    if line.lower().startswith('"path"'):
                        parts = line.split('"')
                        if len(parts) >= 4:
                            p = parts[3].replace("\\\\", "\\")
                            sa = os.path.join(p, "steamapps")
                            if os.path.isdir(sa):
                                paths.append(sa)
            except Exception:
                pass
        sa_default = os.path.join(root, "steamapps")
        if os.path.isdir(sa_default):
            paths.append(sa_default)

    out = []
    for p in paths:
        if p not in out and os.path.isdir(p):
            out.append(p)
    return out

def detect_balatro_dirs() -> list[str]:
    ''' Detect installed Balatro game directories in Steam libraries. '''
    hits = []
    for sa in detect_steam_libraries():
        common = os.path.join(sa, "common")
        if os.path.isdir(common):
            name = "Balatro" # name of the bame folder in Steam library
            p = os.path.join(common, name)
            if os.path.isdir(p):
                hits.append(p)
    seen = set()
    uniq = []
    for h in hits:
        if h not in seen:
            uniq.append(h)
            seen.add(h)
    return uniq

def game_streaming_assets_dir(game_root: str) -> str:
    ''' Get the StreamingAssets directory for the given game root. '''
    if platform.system() == "Darwin":
        if game_root.endswith(".app"):
            return os.path.join(game_root, "Contents", "Resources", "Data", "StreamingAssets")
        return os.path.join(game_root, "Data", "StreamingAssets")
    return os.path.join(game_root, TARGET_RELATIVE)

# Baching up and restoring the game assests if user doesn't want them anymore =========
def ensure_assets_backup(game_root: str):
    ''' Ensure a backup of the StreamingAssets exists, create if not. '''
    backup_root = os.path.join(game_root, BACKUP_DIRNAME)
    if not os.path.isdir(backup_root):
        os.makedirs(backup_root, exist_ok=True)
        src = game_streaming_assets_dir(game_root)
        if os.path.isdir(src):
            copytree_merge(src, os.path.join(backup_root, "StreamingAssets"))
    return backup_root

def restore_assets_backup(game_root: str) -> bool:
    ''' Restore StreamingAssets from backup, return True if restored. '''
    backup_root = os.path.join(game_root, BACKUP_DIRNAME)
    src = os.path.join(backup_root, "StreamingAssets")
    dst = game_streaming_assets_dir(game_root)
    if os.path.isdir(src):
        copytree_merge(src, dst)
        return True
    return False

def backup_file(path: str) -> str:
    ''' Backup a file by copying it to path.bak if not already backed up. '''
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    return bak

def restore_exe_backup(game_root: str) -> bool:
    ''' Restore Balatro.exe from backup, return True if restored. '''
    exe = os.path.join(game_root, EXE_NAME)
    bak = exe + ".bak"
    if os.path.isfile(bak):
        shutil.copy2(bak, exe)
        return True
    return False

# Installation =======================================
def apply_zip_to_dir(zip_path: str, dest_dir: str):
    ''' Apply the contents of a zip file to a destination directory. '''
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            if m.is_dir():
                continue
            if ".." in m.filename or m.filename.startswith(("/", "\\")):
                continue
            out_path = safe_join(dest_dir, m.filename)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with z.open(m) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


# # DOESN'T WORK WITH WAY BALATRO IS PACKAGED ON STEAM
# def install_to_streamingassets(game_root: str, mod_zip_or_url: str) -> str:
#     ''' Install mod zip into StreamingAssets directory. '''
#     ensure_assets_backup(game_root)
#     target_root = game_root
#     if mod_zip_or_url.startswith(("http://", "https://")):
#         tmp = download(mod_zip_or_url)
#         try:
#             apply_zip_to_dir(tmp, target_root)
#         finally:
#             try: os.remove(tmp)
#             except: pass
#     else:
#         apply_zip_to_dir(mod_zip_or_url, target_root)
#     return "Installed mod to StreamingAssets (non-EXE method)."
    

def install_into_exe_archive(game_root: str, mod_zip_or_url: str) -> str:
    ''' Install mod zip into Balatro.exe using 7-Zip. '''
    exe_path = os.path.join(game_root, EXE_NAME)
    if not os.path.isfile(exe_path):
        raise RuntimeError(f"{EXE_NAME} not found in the selected folder.")
    seven_zip = find_7z()
    if not seven_zip:
        raise RuntimeError("7-Zip (7z.exe) not found! Install 7-Zip.")

    tmpzip = None

    mod_zip_path = mod_zip_or_url

    staging = tempfile.mkdtemp(prefix="balatro_mod_")
    try:
        with zipfile.ZipFile(mod_zip_path) as z:
            z.extractall(staging)

        rel_target = os.path.join(staging, "resources", "textures", "2x")
        if not os.path.isdir(rel_target):
            st.info("Note: Zip should mirror EXE layout: resources\\textures\\2x\\...")

        backup_file(exe_path)

        cmd = [
            seven_zip,
            "u", "-y",
            exe_path,
            r"resources\textures\2x\*",
        ]
        res = subprocess.run(cmd, cwd=staging, capture_output=True, text=True) # run the 7z update command to automatically unarchive and update the .exe by dropping in the new images
        if res.returncode != 0:
            raise RuntimeError(f"7z update failed:\n{res.stdout}\n{res.stderr}")

        return "Successfully Modded Balatro with new artwork!" 
    finally: # remove the temporary staging directory
        shutil.rmtree(staging, ignore_errors=True)
        if tmpzip:
            try: os.remove(tmpzip)
            except: pass

# ---- PAGE-SPECIFIC BACKGROUND THEME ----
def apply_page_background(page: str) -> None:
    # Default: let styles.css handle HOME
    if page == "HOME":
        css = """
        <style>
        /* If you want HOME to be different from the global CSS,
           you can override here; otherwise leave this empty block. */
        </style>
        """
    elif "Hearts" in page:
        css = """
        <style>
        .stApp {
            background-image: linear-gradient(to bottom, rgba(147, 0, 0, 0.729), rgba(31, 0, 0, 0.9)),
                      url("https://styles.redditmedia.com/t5_8pimef/styles/bannerBackgroundImage_0e8fxb9funfc1.jpg?format=pjpg&s=caafccccbb631f7b5355254c477dd24869ec196e");
            background-attachment: fixed;
            background-size: cover;
            background-position: center;
        }
        </style>
        """
    elif "Diamonds" in page:
        css = """
        <style>
        .stApp {
            background-image: linear-gradient(to bottom, rgba(169, 56, 0, 0.3), rgba(63, 21, 0, 0.9)),
                      url("https://styles.redditmedia.com/t5_8pimef/styles/bannerBackgroundImage_0e8fxb9funfc1.jpg?format=pjpg&s=caafccccbb631f7b5355254c477dd24869ec196e");
            background-attachment: fixed;
            background-size: cover;
            background-position: center;
        }
        </style>
        """

    elif "Clubs" in page:
        css = """
        <style>
        .stApp {
            
            background-image: linear-gradient(to bottom, rgba(17, 107, 77, 0.3), rgba(0, 37, 20, 0.9)),
                      url("https://styles.redditmedia.com/t5_8pimef/styles/bannerBackgroundImage_0e8fxb9funfc1.jpg?format=pjpg&s=caafccccbb631f7b5355254c477dd24869ec196e");
            background-attachment: fixed;
            background-size: cover;
            background-position: center;
        }
        </style>
        """
    elif "Spades" in page:
        css = """
        <style>
        .stApp {
            background-image: linear-gradient(
                to bottom,
                rgba(0, 40, 90, 0.85),
                rgba(0, 5, 20, 0.95)),
                url("https://styles.redditmedia.com/t5_8pimef/styles/bannerBackgroundImage_0e8fxb9funfc1.jpg?format=pjpg&s=caafccccbb631f7b5355254c477dd24869ec196e");
            background-attachment: fixed;
            background-size: cover;
            background-position: center;
        }
        </style>
        """
    else:
        css = "<style></style>"

    st.markdown(css, unsafe_allow_html=True)



# Per-Suit Page Rendering ==========================
def render_suit_page(suit_key: str) -> None:
    """
    Render the per-suit 'page':
      - show suit title
      - optional high-contrast toggle
      - show card art thumbnails for that suit
      - provide per-suit zip download
      - optional one-click install into Balatro.exe
    """
    suit_title = suit_key.capitalize()
    st.markdown(f"## {suit_title} Card Art")

    # --- High contrast toggle ---
    high_contrast = st.toggle("High Contrast", value=False)

    # --- Show card art previews ---
    hc_or_norm = "hc" if high_contrast else "normal"
    cards_dir = pathlib.Path(__file__).parent / "assets" / "cards" / suit_key / hc_or_norm

    game_root = detect_balatro_dirs()[0] if detect_balatro_dirs() else ""


    # Button to download ================
    # --- Suit-specific zip path ---
    suit_zip_name = f"{suit_key}_art.zip"
    suit_zip_path = pathlib.Path(MODS_DIR) / suit_zip_name

    if not suit_zip_path.is_file():
        st.info(f"No mod zip found for {suit_title} yet "
                f"(looking for `{suit_zip_name}` in `{MODS_DIR}`).")
        return

    if st.button(f"Install {suit_title} Art", key=f"install_{suit_key}"):
        try:
            msg = install_into_exe_archive(game_root, str(suit_zip_path))
            st.success(msg)

        except PermissionError:
            st.error("Permission denied. Run as Administrator if installing under Program Files.")

        except RuntimeError as e:
            # Surface the 7z message, but in a friendlier way
            st.error(f"7-Zip failed while installing {suit_title} art. "
                     "Most likely the zip does not contain a `resources\\textures\\2x` folder "
                     "at its root. Check the zip layout.\n\n"
                     f"Details:\n{e}")
            
        except Exception as e:
            st.error(f"Install failed: {e}")

    if cards_dir.is_dir():
        img_files = sorted(cards_dir.glob("*.png"))
        if img_files:
            cols = st.columns(4)
            for i, img_path in enumerate(img_files):
                with cols[i % 4]:
                    img_html = f"""
<div class="jimbo-wrapper">
  <img class="jimbo-idle tilt-on-hover"
       src="data:image/png;base64,{base64_encode(img_path)}" />
</div>
"""
                    st.markdown(img_html, unsafe_allow_html=True)
        else:
            st.info(f"No card images found yet for {suit_title}.")
    else:
        st.info(f"No card art folder found for {suit_title} (expected {cards_dir}).")

    st.markdown("---")



# Convert labels ======================
def label_to_suit_key(label: str) -> str:
    # Take the last word ("Hearts", "Diamonds", etc.) and lowercase it
    return label.split()[-1].lower()

# Home Page Rendering ========================
def base64_encode(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def render_home_page() -> None:
    """Landing page with jimbo image + centered blurb."""
    jimbo_path = pathlib.Path(__file__).parent / "assets" / "jimbo.png"

    if jimbo_path.is_file():
        img_html = f"""
<div class="jimbo-wrapper">
  <img class="jimbo-idle tilt-on-hover"
       src="data:image/png;base64,{base64_encode(jimbo_path)}" />
</div>
"""
    else:
        img_html = "<p>(Add jimbo.png in the assets/ folder to show the jimbo image here.)</p>"

    html = f"""
<div style="text-align:center; max-width:800px; margin:0 auto;">


  {img_html}

  <h3 style="margin-bottom: 1rem;">
    Welcome to the Balatro Card Art Mod Manager!
  </h3>

  <p>
    This tool helps you manage and customize <strong>card art mods</strong> for Balatro:
  </p>

  <ul style="
      list-style-position: inside;
      padding-left: 0;
      display: inline-block;
      text-align: left;
      margin: 0 auto 1.5rem auto;
  ">
    <li>Browse suit-specific artwork</li>
    <li>Download mod-ready zip files</li>
    <li>Patch your <code>Balatro.exe</code> safely using 7-Zip</li>
    <li>Restore backups with one click</li>
  </ul>

  <p>
    Use the navigation on the left to explore the suits or install your mods.
  </p>

</div>
"""

    st.markdown(html, unsafe_allow_html=True)


def render_restore_page()->None:
    """ Page for restoring backups of original game assets. """

    
    reroll_path = pathlib.Path(__file__).parent / "assets" / "reroll.png"

    if reroll_path.is_file():
        img_html = f"""
                    <div class="jimbo-wrapper">
                    <img class="jimbo-idle tilt-on-hover"
                        src="data:image/png;base64,{base64_encode(reroll_path)}" />
                    </div>
                """
    else:
        img_html = "<p>(Add reroll.png in the assets/ folder to show the image here.)</p>"

    st.markdown(img_html, unsafe_allow_html=True) # add floating reroll

    st.markdown("## Restore Original Game Assets")
    st.text("Restore original card art from backups and remove any modded card art.")

    game_root = detect_balatro_dirs()[0] if detect_balatro_dirs() else ""
    

    valid_game = os.path.isdir(game_root)
    exe_present = os.path.isfile(os.path.join(game_root, EXE_NAME)) if valid_game else False

    if not valid_game:
        st.warning("Enter a valid Balatro install folder before restoring.")
        return

    if not exe_present:
        st.warning(f"{EXE_NAME} not found in that folder.")
        return

    if st.button("Restore Original Assets"):
        try:
            restored_exe = restore_exe_backup(game_root)
            restored_assets = restore_assets_backup(game_root)
            if restored_exe or restored_assets:
                st.success("Successfully restored original game assets!")
            else:
                st.info("No backups found to restore.")
        except Exception as e:
            st.error(f"Restore failed: {e}")

def save_uploaded_zip(upload) -> str:
    """ Save uploaded zip file to a temp location and return its path. """
    tmpf = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmpf.write(upload.read()); tmpf.flush(); tmpf.close()
    return tmpf.name

def render_upload_page()->None:
    """ Page for uploading your own mod zip to install into Balatro.exe. """

    paintbrush_path = pathlib.Path(__file__).parent / "assets" / "paintbrush.png"

    if paintbrush_path.is_file():
        img_html = f"""
                    <div class="jimbo-wrapper">
                    <img class="jimbo-idle tilt-on-hover"
                        src="data:image/png;base64,{base64_encode(paintbrush_path)}" />
                    </div>
                """
    else:
        img_html = "<p>(Add paintbrush.png in the assets/ folder to show the image here.)</p>"

    st.markdown(img_html, unsafe_allow_html=True) # add floating paintbrush
    st.markdown("## Upload Your Own Card Art Mod")
    st.text("Upload a mod .zip file structured for Balatro.exe and install it directly.\nThe zip should follow the structure: `resources\\textures\\2x` folder at its root with the card images as .png inside.")

    game_root = detect_balatro_dirs()[0] if detect_balatro_dirs() else ""
    mod_zip = st.file_uploader("Or upload mod .zip", type=["zip"])
    if st.button("Install uploaded zip", disabled=not (mod_zip is not None)):
        tmp = save_uploaded_zip(mod_zip)
        try:
            with st.status("Patching EXE via 7-Zip...", expanded=True) as s:
                st.write("Backing up Balatro.exe …")
                backup_file(os.path.join(game_root, EXE_NAME))
                st.write("Applying …")
                msg = install_into_exe_archive(game_root, tmp)
                s.update(label="Done", state="complete")
            st.success(msg)

        except PermissionError:
                st.error("Permission denied. Run as Administrator if installing under Program Files.")
        except Exception as e:
            st.error(f"Install failed: {e}")
        finally:
            try: os.remove(tmp)
            except: pass