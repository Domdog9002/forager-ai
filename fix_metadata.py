import os
import shutil
import streamlit

# Get the actual path of your streamlit installation
st_path = os.path.dirname(streamlit.__file__)
dist_info = [f for f in os.listdir(os.path.dirname(st_path)) if f.startswith('streamlit-') and f.endswith('.dist-info')][0]
source = os.path.join(os.path.dirname(st_path), dist_info)

# Force copy the metadata into the local folder PyInstaller uses
target = os.path.join(os.getcwd(), 'streamlit_metadata')
if os.path.exists(target): shutil.rmtree(target)
shutil.copytree(source, target)
print(f"Metadata captured in: {target}")
