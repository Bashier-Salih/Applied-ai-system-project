"""Landing page: simplistic, artistic.

One composition, no data, no forms: gradient wordmark, a single tagline,
the pet photo(s), and one button into the dashboard. Images are embedded
as base64 data URIs from assets/ so they always render.
"""

import streamlit as st

from ui import img_data_uri, landing_hero_src

# Prefer a user-provided assets/landing.{jpg,png,webp}; fall back to the
# bundled dog + cat pair until one is added.
hero = landing_hero_src()
if hero:
    images_html = f"<img class='hero-single' src='{hero}' alt='Cute pets' />"
else:
    dog = img_data_uri("dog.jpg")
    cat = img_data_uri("cat.jpg")
    images_html = (
        f"<img class='hero-a' src='{dog}' alt='Golden retriever' />"
        f"<img class='hero-b' src='{cat}' alt='Cat' />"
    )

st.markdown(
    f"""
    <div class="hero">
        <span class="hero-eyebrow">Daily care, planned</span>
        <span class="hero-title">PawPal+</span>
        <span class="hero-tagline">A deterministic scheduler paired with a grounded AI advisor:
        plan every walk, meal, and brush without the guesswork.</span>
        <div class="hero-images">{images_html}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.container(horizontal_alignment="center"):
    if st.button("Open dashboard", icon=":material/arrow_forward:"):
        st.switch_page("app_pages/dashboard.py")

with st.container(horizontal_alignment="center"):
    st.caption("Grounded answers only: every AI claim cites a source from the care knowledge base.")
