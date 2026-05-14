import os
import streamlit as st

# 1. Path to your modules
THEME_DIR = r"C:\Apps\theme_rules"

def get_available_themes():
    # Automatically list all .txt files in the folder (minus the .txt extension)
    if not os.path.exists(THEME_DIR):
        os.makedirs(THEME_DIR)
    return [f.replace(".txt", "") for f in os.listdir(THEME_DIR) if f.endswith(".txt")]

# 2. The Dashboard UI
st.title("🛡️ Modpack Architect: Theme Sync")

# Auto-syncing list: any new file you add to C:\Apps\theme_rules shows up here instantly
available_themes = get_available_themes()

selected_themes = st.multiselect(
    "Select Active Themes for this Pack:",
    options=available_themes,
    help="These tags are synced directly from your C:/Apps/theme_rules folder."
)

# 3. Building the "Combined Brain"
def build_context(themes):
    combined_instructions = "You are a Modpack Development Expert. \n"
    for theme in themes:
        with open(os.path.join(THEME_DIR, f"{theme}.txt"), "r") as f:
            combined_instructions += f"\n[Active Theme: {theme.upper()}]\n{f.read()}\n"
    return combined_instructions

if selected_themes:
    current_context = build_context(selected_themes)
    # This 'current_context' is what gets sent to Llama 3
    import os

# This points to your actual themes folder
THEME_DIR = r"C:\Apps\Forager ai\theme_rules"

def load_active_themes(selected_list):
    combined_rules = ""
    for theme in selected_list:
        file_path = os.path.join(THEME_DIR, f"{theme}.txt")
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                combined_rules += f"\n--- {theme.upper()} RULES ---\n" + f.read()
    return combined_rules

# CHANGE THESE NAMES TO SWITCH MODPACK TYPES
my_active_tags = ["industrial", "rpg", "magic"] 
active_context = load_active_themes(my_active_tags)

print(f"Forager AI is now running with: {my_active_tags}")
import os

# Your specific theme directory
THEME_DIR = r"C:\Apps\Forager ai\theme_rules"

def auto_sync_themes():
    """Dynamically finds all .txt theme files in your folder."""
    if not os.path.exists(THEME_DIR):
        return []
    # Automatically gets: sci-fi, survival, tech, adventure, etc.
    return [f.replace(".txt", "") for f in os.listdir(THEME_DIR) if f.endswith(".txt")]

def get_modpack_context(folder_path):
    """Detects the modpack type based on its name or a hidden tag file."""
    available_themes = auto_sync_themes()
    detected_themes = []
    
    # Check if the folder name matches one of your themes (e.g., 'My-RPG-Pack')
    folder_name = os.path.basename(folder_path).lower()
    for theme in available_themes:
        if theme in folder_name:
            detected_themes.append(theme)
            
    return detected_themes

# Example Usage: Point this to your active modpack
current_pack = r"C:\Users\Dom Carlstrom\curseforge\minecraft\Instances\My-Industrial-World"
active_tags = get_modpack_context(current_pack)

print(f"Forager AI Syncing Themes: {active_tags}")