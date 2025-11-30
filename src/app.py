# streamlit_app.py
import mod_support_func as msf
import streamlit as st


# Search bar icon ===============
st.set_page_config(page_title=msf.APP_NAME, page_icon="🃏", layout="wide") # browser icon and title

st.markdown("""
<link href="https://fonts.googleapis.com/css?family=Rancho&effect=anaglyph" rel="stylesheet">
""", unsafe_allow_html=True)

# Load custom CSS from styles.css ============
msf.local_css("assets/styles.css") # load in the styles

# ---- GLOBAL MOTION TOGGLE ----
disable_motion = st.sidebar.toggle("DISABLE MOTION", value=False, key="disable_motion", width="stretch")

if disable_motion:
    st.markdown(
        """
        <style>
          /* Kill idle animations */
          .jimbo-idle,
          .title-idle {
              animation: none !important;
          }

          /* Kill wobble / transforms / transitions on hover */
          .tilt-on-hover,
          .title-floater {
              transition: none !important;
              transform: none !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


# floating title ==========================================
st.markdown(
    """
    <div style="text-align:center;">
        <h1 class="title-floater title-idle"
            data-title="Balatro Card Art Mod Manager"
            style="font-family: Rancho; display:inline-block;">
            Balatro Card Art Mod Manager
        </h1>
    </div>
    """,
    unsafe_allow_html=True
)


# Sidebar =================
suits = ["HOME", "♥ Hearts", "♦ Diamonds", "♣ Clubs", "♠ Spades", "Restore Original"]
st.sidebar.title("Card Suits")
selected_category = st.sidebar.radio("Select a Suit",suits) # create a category selector as a sidebar
msf.apply_page_background(selected_category) # apply background based on selected category
# PAGE ROUTING ===
if selected_category.startswith("HOME"):
    # home page
    msf.render_home_page()

elif selected_category == "Restore Original":
    # restore from backup all of original art
    msf.render_restore_page()

else:
    # Suit pages
    selected_suit_key = msf.label_to_suit_key(selected_category)
    msf.render_suit_page(selected_suit_key)

st.divider()


if getattr(msf.sys, "frozen", False):
    pass
