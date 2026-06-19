#!/usr/bin/env python3
"""
YouTube Facial Emotion Analyzer (DeepFace edition)
====================================================
Downloads a YouTube video/short and analyzes facial emotion frame-by-frame
using DeepFace. Runs fully locally/offline after the first model download
-- no API key, no account, no service that can be sunset out from under you.

Detects: angry, disgust, fear, happy, sad, surprise, neutral
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # quiet TensorFlow's startup chatter

import cv2
import yt_dlp
from deepface import DeepFace

EMOTION_LABELS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]


class YouTubeFaceEmotionAnalyzer:
    def __init__(self, output_dir: str = "./emotion_analysis"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download_youtube_video(self, url: str) -> str:
        print(f"[*] Downloading YouTube video from:\n    {url}")
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = ydl.prepare_filename(info)
        title = info.get("title", "Unknown title")
        print(f"[\u2713] Downloaded: {title}")
        return video_path

    def analyze_emotions(self, video_path: str, sample_every_n_seconds: float = 1.0,
                          detector_backend: str = "opencv") -> list:
        print("[*] Opening video for frame sampling...")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps else 0
        frame_interval = max(int(fps * sample_every_n_seconds), 1)

        print(f"    Video: {duration:.1f}s @ {fps:.1f}fps ({total_frames} frames)")
        print(f"    Sampling every {sample_every_n_seconds}s (~every {frame_interval} frames)")
        print("[*] Running DeepFace emotion analysis (first run downloads model weights)...")

        results = []
        frame_idx = 0
        sampled_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp = frame_idx / fps
                sampled_count += 1
                try:
                    faces = DeepFace.analyze(
                        img_path=frame,
                        actions=["emotion"],
                        enforce_detection=False,
                        detector_backend=detector_backend,
                        silent=True,
                    )
                except Exception:
                    faces = []

                for face in faces:
                    if face.get("face_confidence", 0) <= 0:
                        continue
                    results.append({
                        "timestamp": round(timestamp, 2),
                        "dominant_emotion": face.get("dominant_emotion"),
                        "emotion": face.get("emotion"),
                        "face_confidence": face.get("face_confidence"),
                    })
                print(f"    [{timestamp:.1f}s] sampled ({sampled_count} frames so far)", end="\r")

            frame_idx += 1

        cap.release()
        print()
        print(f"[\u2713] Sampled {sampled_count} frames, detected a face in {len(results)} of them")
        return results

    def process_predictions(self, frame_results: list, top_n: int = 7) -> dict:
        print("[*] Processing predictions...")
        acc = {label: {"sum": 0.0, "n": 0} for label in EMOTION_LABELS}

        for r in frame_results:
            for label, score in (r.get("emotion") or {}).items():
                bucket = acc.setdefault(label, {"sum": 0.0, "n": 0})
                bucket["sum"] += score
                bucket["n"] += 1

        averaged = {name: (v["sum"] / v["n"]) for name, v in acc.items() if v["n"]}
        ranked = sorted(averaged.items(), key=lambda kv: kv[1], reverse=True)
        face_emotions = {name: round(score, 2) for name, score in ranked[:top_n]}

        dominant_counts = {}
        for r in frame_results:
            d = r.get("dominant_emotion")
            if d:
                dominant_counts[d] = dominant_counts.get(d, 0) + 1

        return {
            "timestamp": datetime.now().isoformat(),
            "frames_with_faces": len(frame_results),
            "face_emotions": face_emotions,
            "dominant_emotion_counts": dominant_counts,
            "frame_by_frame": frame_results,
        }

    def print_summary(self, summary: dict) -> None:
        print("\n" + "=" * 60)
        print("FACIAL EMOTION ANALYSIS RESULTS")
        print("=" * 60)
        print(f"\nFrames with a detected face: {summary['frames_with_faces']}")

        print("\n[AVERAGE EMOTION SCORES]")
        if not summary["face_emotions"]:
            print("  (no faces detected -- try --detector retinaface for higher "
                  "accuracy, or use a video with a clearer/closer face)")
        else:
            for name, score in summary["face_emotions"].items():
                print(f"  {name:<12} {score:.1f}%")

        print("\n[DOMINANT EMOTION ACROSS FRAMES]")
        counts = summary["dominant_emotion_counts"]
        total = sum(counts.values()) or 1
        for name, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  {name:<12} {n} frames ({n / total * 100:.0f}%)")
        print("\n" + "=" * 60)

    def save_results(self, summary: dict, filename: str = None) -> str:
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"emotion_analysis_{ts}.json"
        path = self.output_dir / filename
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"[\u2713] Saved detailed results to {path}")
        return str(path)


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze facial emotions in a YouTube video using DeepFace (local, offline).")
    parser.add_argument("youtube_url", help="YouTube video URL")
    parser.add_argument("--output-dir", default="./emotion_analysis", help="Directory to save video and results")
    parser.add_argument("--sample-every", type=float, default=1.0, help="Seconds between sampled frames (default: 1.0)")
    parser.add_argument("--detector", default="opencv", help="Face detector backend: opencv (fastest), retinaface (most accurate), mtcnn, ssd")
    parser.add_argument("--save-json", action="store_true", help="Save detailed results to JSON")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        analyzer = YouTubeFaceEmotionAnalyzer(output_dir=args.output_dir)
        video_path = analyzer.download_youtube_video(args.youtube_url)
        frame_results = analyzer.analyze_emotions(video_path, sample_every_n_seconds=args.sample_every, detector_backend=args.detector)
        summary = analyzer.process_predictions(frame_results)
        analyzer.print_summary(summary)
        if args.save_json:
            analyzer.save_results(summary)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()