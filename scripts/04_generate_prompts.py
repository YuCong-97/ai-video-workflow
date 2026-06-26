from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate prompt CSV from storyboard and configs.")
    parser.add_argument("--config", default="input/config/project.yaml")
    parser.add_argument("--episode", default="ep01")
    parser.add_argument("--scene")
    parser.add_argument("--shot")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[TODO] generate_prompts episode={args.episode} scene={args.scene} shot={args.shot}")


if __name__ == "__main__":
    main()

