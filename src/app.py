# streamlit_app.py
import mod_support_func as msf
import streamlit as st

# UI ==========================================
st.set_page_config(page_title=msf.APP_NAME, page_icon="🃏", layout="centered") # browser icon and title
st.title("Balatro Mod Manager")

# Section: Download your mod zips ==============
st.subheader("*Requires 7zip for Mod Installation*")
st.subheader("Download 7zip: https://www.7-zip.org/") # link for 7zip install
mods_list = []
if msf.os.path.isdir(msf.MODS_DIR): # add the mods .zips here!!!!
    for name in sorted(msf.os.listdir(msf.MODS_DIR)):
        path = msf.os.path.join(msf.MODS_DIR, name)
        if msf.os.path.isfile(path) and name.lower().endswith(".zip"):
            mods_list.append((name, path))

if not mods_list:
    st.info("No mod zips found. Add files under a `mods/` folder")
else:
    names = [n for n, _ in mods_list]
    selected_name = st.selectbox("Choose a mod zip to download", names)
    selected_path = dict(mods_list)[selected_name]
    size_mb = msf.os.path.getsize(selected_path) / (1024 * 1024)
    sha = msf.file_sha256(selected_path)
    st.caption(f"File size: {size_mb:.2f} MB — SHA-256: `{sha}`")
    with open(selected_path, "rb") as f:
        st.download_button(
            label=f"Download {selected_name}",
            data=f.read(),
            file_name=selected_name,
            mime="application/zip",
            type="primary",
        )

st.divider()

# Section: Install ========================
st.subheader("Install mod into your local Balatro")

detected = msf.detect_balatro_dirs() # detecting if Balatro game directory exists
default_game = detected[0] if detected else ""
game_root = st.text_input(
    "Balatro game folder",
    value=default_game,
    placeholder=r"C:\Program Files (x86)\Steam\steamapps\common\Balatro",
    help="Select the folder that contains Balatro.exe"
)
valid_game = msf.os.path.isdir(game_root)
exe_present = msf.os.path.isfile(msf.os.path.join(game_root, msf.EXE_NAME)) if valid_game else False
assets_dir = msf.game_streaming_assets_dir(game_root) if valid_game else ""

if valid_game:
    if exe_present:
        st.success(f"Found {msf.EXE_NAME} in: {game_root}")
    else:
        st.warning(f"{msf.EXE_NAME} not found in that folder (macmsf.msf.os/flatpak/manual install?).")
    st.caption(f"StreamingAssets path (non-EXE method): {assets_dir}")
else:
    st.warning("Enter a valid Balatro install folder (Steam -> Manage -> Browse local files).")

st.subheader("Install method")
method = st.radio(
    "Install target",
    options=["EXE Archive (7-Zip)"], # If I want to add other methods through the radio button i cand add it to the list
    index=0,
    help="EXE Archive updates resources\\textures\\2x inside Balatro.exe via 7-Zip. StreamingAssets copies files externally."
)
if method == "EXE Archive (7-Zip)":
    st.info("Requires 7-Zip CLI (7z.exe)!")

st.subheader("Pick a mod zip to install")
col1, col2 = st.columns([1,1], gap="large")

with col1:
    # Install from a bundled mod in /mods
    if mods_list:
        bundled_choice = st.selectbox("Bundled zips (from `mods/`)", ["(none)"] + [n for n,_ in mods_list])
        if st.button("Install selected bundled zip", disabled=not (valid_game and bundled_choice != "(none)")):
            path = dict(mods_list)[bundled_choice]
            try:
                if method == "EXE Archive (7-Zip)":
                    with st.status("Patching EXE via 7-Zip...", expanded=True) as s:
                        st.write("Backing up Balatro.exe …")
                        msf.backup_file(msf.os.path.join(game_root, msf.EXE_NAME))
                        st.write("Applying update to resources\\textures\\2x …")
                        msg = msf.install_into_exe_archive(game_root, path)
                        s.update(label="Done", state="complete")
                    st.success(msg)

            except PermissionError:
                st.error("Permission denied. Run as Administrator if installing under Program Files.")
            except Exception as e:
                st.error(f"Install failed: {e}")

with col2: # Install from uploaded file Can upload your own mods??? Maybe do this???
    mod_zip = st.file_uploader("Or upload mod .zip", type=["zip"])
    if st.button("Install uploaded zip", disabled=not (valid_game and mod_zip is not None)):
        def _save_uploaded_zip(upload) -> str:
            tmpf = msf.tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmpf.write(upload.read()); tmpf.flush(); tmpf.close()
            return tmpf.name
        tmp = _save_uploaded_zip(mod_zip)
        try:
            if method == "EXE Archive (7-Zip)":
                with st.status("Patching EXE via 7-Zip...", expanded=True) as s:
                    st.write("Backing up Balatro.exe …")
                    msf.backup_file(msf.os.path.join(game_root, msf.EXE_NAME))
                    st.write("Applying …")
                    msg = msf.install_into_exe_archive(game_root, tmp)
                    s.update(label="Done", state="complete")
                st.success(msg)

        except PermissionError:
            st.error("Permission denied. Run as Administrator if installing under Program Files.")
        except Exception as e:
            st.error(f"Install failed: {e}")
        finally:
            try: msf.os.remove(tmp)
            except: pass

st.divider()
st.subheader("Uninstall / restore originals")
c1 = st.columns(1)
if c1:
    if st.button("Restore EXE from .bak"):
        try:
            if msf.restore_exe_backup(game_root):
                st.success("Restored Balatro.exe from backup.")
            else:
                st.warning("No Balatro.exe.bak found.")
        except Exception as e:
            st.error(f"Restore failed: {e}")


st.divider()

if getattr(msf.sys, "frozen", False):
    pass
