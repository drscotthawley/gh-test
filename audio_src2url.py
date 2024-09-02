#!/usr/bin/env python3

import json
import re
import sys
import os
import base64
import hashlib
import subprocess



# Function to save base64 audio data to a file
def save_audio_file(base64_data, notebook_name, cell_index, hash_length=64):
    # Decode the base64 data
    audio_data = base64.b64decode(base64_data)
    # Generate a unique hash for the audio data
    audio_hash = hashlib.sha256(audio_data).hexdigest()[:hash_length] if hash_length > 0 else ""
    # Generate the filename
    audio_filename = f"{notebook_name}_cell{cell_index}_{audio_hash}.wav"
    audio_filepath = os.path.join("audio_files", audio_filename)
    # Save the audio file
    with open(audio_filepath, 'wb') as audio_file:
        audio_file.write(audio_data)
    return audio_filepath



# Function to commit and push the audio file to the 'audio-storage' branch
def commit_and_push_audio_file(audio_filepath):
    branch_name = "audio-storage"
    try:
        # Get the current branch name
        current_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip()
        
        # Check if the branch exists
        branch_exists = subprocess.run(["git", "rev-parse", "--verify", branch_name], capture_output=True, text=True).returncode == 0
        if not branch_exists:
            # Create the branch if it doesn't exist
            subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        else:
            # Checkout the branch if it exists
            subprocess.run(["git", "checkout", branch_name], check=True)
        
        # Add the audio file to the git index
        subprocess.run(["git", "add", audio_filepath], check=True)
        # Commit the audio file
        subprocess.run(["git", "commit", "-m", f"Add audio file {audio_filepath}"], check=True)
        # Push the branch to GitHub
        subprocess.run(["git", "push", "origin", branch_name], check=True)
        # Get the URL of the raw version of the audio file
        repo_url = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=True).stdout.strip()
        raw_url = f"{repo_url.replace('.git', '')}/raw/{branch_name}/{audio_filepath}"
        
        # Switch back to the original branch
        subprocess.run(["git", "checkout", current_branch], check=True)
        
        return raw_url
    except subprocess.CalledProcessError as e:
        print(f"Error during Git operation: {e}")
        return None



# Function to process a single notebook file
def audio_src2url(input_filename, nondestructive=True):
    # Generate the output filename
    if nondestructive:
        output_filename = re.sub(r'\.ipynb$', '_out.ipynb', input_filename)
    else:
        output_filename = input_filename

    # Load the Jupyter Notebook file
    try:
        with open(input_filename, 'r') as file:
            notebook = json.load(file)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return

    # Directory to save the audio files
    audio_dir = "audio_files"
    os.makedirs(audio_dir, exist_ok=True)

    url_index = 0
    matches_found = False

    # Function to replace base64 audio data with URLs and save audio files
    def replace_audio_data(cell, cell_index):
        nonlocal url_index, matches_found
        if cell['cell_type'] == 'code':
            for output in cell.get('outputs', []):
                if output['output_type'] == 'execute_result':
                    for key, value in output.get('data', {}).items():
                        if key == 'text/html':
                            # Join the list of strings into a single string
                            value_str = ''.join(value)
                            # Find all <source> elements with base64 audio data
                            matches = re.findall(r'<source src="data:audio/[^"]+base64,([^"]+)"', value_str)
                            if matches:
                                matches_found = True
                                for match in matches:
                                    # Save the audio file and get the file path
                                    audio_filepath = save_audio_file(match, os.path.splitext(os.path.basename(input_filename))[0], cell_index)
                                    # Commit and push the audio file to the 'audio-storage' branch
                                    raw_url = commit_and_push_audio_file(audio_filepath)
                                    if raw_url:
                                        # Replace base64 data with raw URL
                                        new_source = f'<source src="{raw_url}"'
                                        value_str = value_str.replace(f'data:audio/wav;base64,{match}', raw_url)
                                        print(f"Replacing base64 data with {new_source}")
                            output['data'][key] = [value_str]

    # Traverse the notebook cells
    for cell_index, cell in enumerate(notebook['cells']):
        replace_audio_data(cell, cell_index)

    # Save the modified notebook back to the file
    with open(output_filename, 'w') as file:
        json.dump(notebook, file, indent=2)

    # Output the result
    if matches_found:
        print(f"Matches found and replaced. Output saved to {output_filename}")
    else:
        print("No matches found.")



if __name__ == "__main__":
    # Check if the input filename(s) or directory is provided
    if len(sys.argv) < 2:
        print("Usage: audio_src2url.py <input_filename.ipynb> [<input_filename2.ipynb> ...] or <directory>")
        sys.exit(1)

    # Process each argument
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            # Process all .ipynb files in the directory
            for root, _, files in os.walk(arg):
                for file in files:
                    if file.endswith('.ipynb'):
                        audio_src2url(os.path.join(root, file))
        elif os.path.isfile(arg) and arg.endswith('.ipynb'):
            # Process the individual .ipynb file
            audio_src2url(arg)
        else:
            print(f"Skipping invalid file or directory: {arg}")