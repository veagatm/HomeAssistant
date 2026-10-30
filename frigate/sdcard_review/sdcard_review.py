#!/usr/bin/env python3
"""
Reolink SD Card Review Helper

Pulls event clips directly from camera onboard SD cards via the camera's own
HTTPS API — bypasses Frigate and the Mac Mini's disk entirely. Built 2026-07-08
as an on-demand review source: Frigate purges events faster than expected
("Event not found" seen on events only ~2 weeks old), while the cameras'
onboard SD cards independently hold ~7-9 days of AI-triggered clips (person/
vehicle/dog-cat/motion). Only `front` and `floodlight` have SD cards installed
— `backyard` does not.

This is a review tool, not a pipeline: nothing here runs continuously or
stores anything long-term. Pull a clip only when there's something specific
to look at, extract frames, then discard.

Usage:
    python3 sdcard_review.py search   <camera> <start> <end>
    python3 sdcard_review.py download <camera> <clip_name> <out_path>
    python3 sdcard_review.py frames   <video_path> [--count N] [--outdir DIR]
    python3 sdcard_review.py review   <camera> <start> <end> [--outdir DIR] [--frames-per-clip N]

<camera>       one of: front, backyard, floodlight
<start>/<end>  "YYYY-MM-DD HH:MM:SS" (camera's local time)

Credentials read from ~/frigate/.env (CAMERA_<NAME>_IP / CAMERA_<NAME>_PASS).
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()  # cameras use a self-signed cert

ENV_PATH = os.path.expanduser("~/frigate/.env")
CAMERAS = ["front", "backyard", "floodlight"]


def load_env():
    env = {}
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v
    return env


def camera_creds(camera: str, env: dict):
    key = camera.upper()
    ip = env.get(f"CAMERA_{key}_IP")
    password = env.get(f"CAMERA_{key}_PASS")
    if not ip or not password or password == "changeme":
        raise SystemExit(f"No credentials for camera '{camera}' in {ENV_PATH}")
    return ip, password


def dt_to_reolink(dt: datetime) -> dict:
    return {"year": dt.year, "mon": dt.month, "day": dt.day,
            "hour": dt.hour, "min": dt.minute, "sec": dt.second}


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def search_clips(ip, password, start: datetime, end: datetime, stream="sub"):
    """List recorded clips in [start, end]. Reolink's Search silently returns
    empty for windows longer than roughly a day — use search_clips_ranged for
    anything wider than that."""
    url = f"https://{ip}/cgi-bin/api.cgi?cmd=Search&user=admin&password={password}"
    body = [{
        "cmd": "Search", "action": 0,
        "param": {"Search": {
            "channel": 0, "onlyStatus": 0, "streamType": stream,
            "StartTime": dt_to_reolink(start), "EndTime": dt_to_reolink(end),
        }}
    }]
    resp = requests.post(url, json=body, verify=False, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data[0].get("code") != 0:
        raise RuntimeError(f"Search failed: {data}")
    return data[0]["value"]["SearchResult"].get("File", [])


def search_clips_ranged(ip, password, start: datetime, end: datetime, stream="sub"):
    """Chunk a multi-day range into per-day Search calls."""
    all_files = []
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day_start <= end:
        day_end = min(day_start.replace(hour=23, minute=59, second=59), end)
        chunk_start = max(day_start, start)
        all_files.extend(search_clips(ip, password, chunk_start, day_end, stream))
        day_start += timedelta(days=1)
    return all_files


def download_clip(ip, password, clip_name: str, out_path: str):
    url = (f"https://{ip}/cgi-bin/api.cgi?cmd=Download&user=admin&password={password}"
           f"&source={clip_name}&output={os.path.basename(out_path)}")
    resp = requests.get(url, verify=False, timeout=60, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return out_path


def extract_frames(video_path: str, outdir: str, count: int = 5):
    """Extract `count` evenly-spaced frames from a clip using ffmpeg."""
    os.makedirs(outdir, exist_ok=True)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        duration = 0

    stem = Path(video_path).stem
    out_paths = []
    if duration <= 0:
        out_path = os.path.join(outdir, f"{stem}_f0.jpg")
        subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vframes", "1", out_path],
                        capture_output=True)
        if os.path.exists(out_path):
            out_paths.append(out_path)
        return out_paths

    for i in range(count):
        ts = duration * (i + 0.5) / count
        out_path = os.path.join(outdir, f"{stem}_f{i}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(ts), "-i", video_path, "-vframes", "1", out_path],
            capture_output=True,
        )
        if os.path.exists(out_path):
            out_paths.append(out_path)
    return out_paths


def cmd_search(args):
    env = load_env()
    ip, password = camera_creds(args.camera, env)
    start, end = parse_dt(args.start), parse_dt(args.end)
    files = search_clips_ranged(ip, password, start, end)
    for f in files:
        st, et = f["StartTime"], f["EndTime"]
        print(f"{st['year']}-{st['mon']:02d}-{st['day']:02d} "
              f"{st['hour']:02d}:{st['min']:02d}:{st['sec']:02d} - "
              f"{et['hour']:02d}:{et['min']:02d}:{et['sec']:02d}  "
              f"({int(f['size']) / 1024:.0f} KB)  {f['name']}")
    print(f"\n{len(files)} clip(s) found", file=sys.stderr)


def cmd_download(args):
    env = load_env()
    ip, password = camera_creds(args.camera, env)
    out = download_clip(ip, password, args.clip_name, args.out_path)
    print(out)


def cmd_frames(args):
    frames = extract_frames(args.video_path, args.outdir, args.count)
    for f in frames:
        print(f)


def cmd_review(args):
    """One-shot: search a window, download every clip found, extract frames from each."""
    env = load_env()
    ip, password = camera_creds(args.camera, env)
    start, end = parse_dt(args.start), parse_dt(args.end)
    files = search_clips_ranged(ip, password, start, end)
    if not files:
        print("No clips found in that window.", file=sys.stderr)
        return
    os.makedirs(args.outdir, exist_ok=True)
    for f in files:
        name = f["name"]
        local_path = os.path.join(args.outdir, os.path.basename(name))
        print(f"Downloading {name} -> {local_path}", file=sys.stderr)
        download_clip(ip, password, name, local_path)
        for fr in extract_frames(local_path, args.outdir, args.frames_per_clip):
            print(fr)


def main():
    p = argparse.ArgumentParser(description="Reolink SD card review helper")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("search", help="List clips in a time window")
    sp.add_argument("camera", choices=CAMERAS)
    sp.add_argument("start", help='"YYYY-MM-DD HH:MM:SS"')
    sp.add_argument("end", help='"YYYY-MM-DD HH:MM:SS"')
    sp.set_defaults(func=cmd_search)

    dp = sub.add_parser("download", help="Download one clip by name")
    dp.add_argument("camera", choices=CAMERAS)
    dp.add_argument("clip_name", help="e.g. Mp4Record/2026-07-06/RecS03_....mp4")
    dp.add_argument("out_path")
    dp.set_defaults(func=cmd_download)

    fp = sub.add_parser("frames", help="Extract frames from a downloaded clip")
    fp.add_argument("video_path")
    fp.add_argument("--outdir", default=".")
    fp.add_argument("--count", type=int, default=5)
    fp.set_defaults(func=cmd_frames)

    rp = sub.add_parser("review", help="Search + download + extract frames in one shot")
    rp.add_argument("camera", choices=CAMERAS)
    rp.add_argument("start", help='"YYYY-MM-DD HH:MM:SS"')
    rp.add_argument("end", help='"YYYY-MM-DD HH:MM:SS"')
    rp.add_argument("--outdir", default="./sdcard_review_out")
    rp.add_argument("--frames-per-clip", type=int, default=3)
    rp.set_defaults(func=cmd_review)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
