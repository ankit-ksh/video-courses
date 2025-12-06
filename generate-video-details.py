import json
import subprocess
from pathlib import Path
from datetime import datetime

# Input root folder
PLAYLIST_INPUT_DIR = Path("./playlists")

# Output base folder
OUTPUT_BASE_DIR = Path("./playlist_videos")

# Output indexes at project root
MASTER_LIST_FILE = Path("./master_list.json")
TAGS_INDEX_FILE = Path("./tags_index.json")
SCHEMA_FILE = Path("./schema.json")

# GLOBAL accumulators
MASTER_LIST = []
TAGS_INDEX = {}

# ---------------------------------------------
# Utility: Load old version if exists
# ---------------------------------------------
def load_existing_version(output_file):
    if output_file.exists():
        try:
            with open(output_file, "r") as f:
                return json.load(f).get("version", 0)
        except:
            return 0
    return 0


# ---------------------------------------------
# YouTube extraction
# ---------------------------------------------
def fetch_youtube_flat_playlist(playlist_id):
    url = f"https://www.youtube.com/playlist?list={playlist_id}"

    result = subprocess.run(
        ["yt-dlp", "-J", "--flat-playlist", "--no-warnings", url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(f"[ERROR] yt-dlp failed for YouTube playlist: {playlist_id}")
        print(result.stderr)
        return None

    return json.loads(result.stdout)


def process_youtube_playlist(entry, output_file):
    playlist_id = entry["playlist_id"]

    data = fetch_youtube_flat_playlist(playlist_id)
    if data is None:
        return None

    playlist_title = data.get("title") or entry.get("playlist_name", "Untitled Playlist")

    videos = [
        {"video_id": v.get("id"), "title": v.get("title") or "Untitled Video"}
        for v in data.get("entries", [])
    ]

    old_version = load_existing_version(output_file)
    new_version = old_version + 1

    return {
        "playlist_id": playlist_id,
        "provider": "youtube",
        "version": new_version,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "title": playlist_title,
        "subtype": entry.get("subtype", []),
        "tags": entry.get("tags", []),
        "videos": videos
    }


# ---------------------------------------------
# Placeholder for future Internet Archive
# ---------------------------------------------
def process_archive_playlist(entry, output_file):
    print(f"[SKIPPED] Internet Archive not implemented: {entry['playlist_id']}")
    return None


# ---------------------------------------------
# MAIN SCRIPT
# ---------------------------------------------
def main():
    json_files = list(PLAYLIST_INPUT_DIR.rglob("*.json"))
    if not json_files:
        print("No playlist files found.")
        return

    for json_file in json_files:
        print(f"\n[PROCESSING INPUT FILE] {json_file}")

        with open(json_file, "r") as f:
            entries = json.load(f)

        relative_path = json_file.relative_to(PLAYLIST_INPUT_DIR).parent
        input_filename = json_file.stem
        output_dir = OUTPUT_BASE_DIR / relative_path / input_filename
        output_dir.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            playlist_id = entry["playlist_id"]
            provider = entry.get("provider", "youtube")

            out_file = output_dir / f"{playlist_id}.json"

            print(f"  → Processing {provider}: {playlist_id}")

            if provider == "youtube":
                final_json = process_youtube_playlist(entry, out_file)
            elif provider == "internet-archive":
                final_json = process_archive_playlist(entry, out_file)
            else:
                print(f"  [SKIPPED] Unknown provider: {provider}")
                continue

            if final_json is None:
                print(f"  [FAILED] {playlist_id}")
                continue

            with open(out_file, "w") as f:
                json.dump(final_json, f, indent=2)

            print(f"     ✔ Saved v{final_json['version']} → {out_file}")

            # Accumulate into MASTER LIST
            MASTER_LIST.append({
                "playlist_id": final_json["playlist_id"],
                "provider": final_json["provider"],
                "title": final_json["title"],
                "subtype": final_json["subtype"],
            })

            # Build TAG INDEX
            for tag in final_json["tags"]:
                TAGS_INDEX.setdefault(tag.lower(), []).append(final_json["playlist_id"])


    # ---------------------------------------------
    # SAVE MASTER LIST + TAG INDEX + SCHEMA
    # ---------------------------------------------
    print("\n[WRITING GLOBAL INDEX FILES]")

    with open(MASTER_LIST_FILE, "w") as f:
        json.dump(MASTER_LIST, f, indent=2)
    print("  ✔ master_list.json created")

    with open(TAGS_INDEX_FILE, "w") as f:
        json.dump(TAGS_INDEX, f, indent=2)
    print("  ✔ tags_index.json created")

    schema = {
        "playlist_id": "string",
        "provider": ["youtube", "internet-archive"],
        "version": "number",
        "last_updated": "string",
        "title": "string",
        "subtype": ["string"],
        "tags": ["string"],
        "videos": [
            {"video_id": "string", "title": "string"}
        ]
    }

    with open(SCHEMA_FILE, "w") as f:
        json.dump(schema, f, indent=2)
    print("  ✔ schema.json created")


if __name__ == "__main__":
    main()

