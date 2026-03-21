"""Run Claude Code CLI and stream its output."""

import json
import subprocess
import sys


def stream_claude(prompt: str) -> str:
    """Run claude with streaming JSON output and print text chunks as they arrive."""
    proc = subprocess.Popen(
        ["claude", "-p", "--output-format", "stream-json", "--verbose", prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    collected = []
    assert proc.stdout is not None  # guaranteed by stdout=subprocess.PIPE
    for raw_line in proc.stdout:
        line = raw_line.decode().strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "assistant":
            message = event.get("message", {})
            for block in message.get("content", []):
                if block.get("type") == "text":
                    text = block["text"]
                    print(text, end="", flush=True)
                    collected.append(text)

        if event.get("type") == "result" and event.get("is_error"):
            print(event.get("result", "Unknown error"), file=sys.stderr)

    proc.wait()
    print()

    if proc.returncode != 0 and proc.stderr:
        stderr = proc.stderr.read().decode()
        print(f"claude exited with code {proc.returncode}: {stderr}", file=sys.stderr)

    return "".join(collected)


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Say hello in exactly 5 words."
    response = stream_claude(prompt)
    print(f"\n--- Full response ({len(response)} chars) ---")
    print(response)
