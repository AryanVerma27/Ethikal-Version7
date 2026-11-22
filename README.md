# Oval Warden

Oval Warden is a Python bot for the Builders Buildathon Mech Royale track. It uses the official kit's Python protocol wrapper and reads the official map at startup. It has no third-party Python dependencies.

The bot farms cubes from nearby crates and drones, looks for supply drops, and disengages when damaged or outnumbered. It adapts its secondary weapon priorities to enemy weapons, distance, and energy. It leads moving targets, checks whether terrain or buildings obstruct shots, plans detours around obstacles, and budgets travel time ahead of the closing circle.

## Verify

Extract the official starter kit separately. From the extracted kit folder, point the checker at this source directory:

```sh
BOT_DIR=/absolute/path/to/oval-warden
python3 check/check.py -- python3 -B -u "$BOT_DIR/bot.py"

docker build --platform linux/amd64 -t oval-warden "$BOT_DIR"
python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 \
  --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m \
  --user 65534:65534 -v "$PWD/arena:/arena:ro" oval-warden
```

The checker replays observations and verifies protocol compliance. Practice scores come from the track's 48 matches.

On Windows, the original kit checker applies `os.path.abspath` to
`--map-dir /arena`, turning the Linux container path into `C:\arena`.
In your local copy of `check/check.py`, change the assignment to
`hello["map"]["dir"] = a.map_dir` before running the container check.
Successful startup reports `name 'Oval Warden Ascend'`.

## Enter

Commit the contents of this directory to a public GitHub repository. Keep the Dockerfile at the repository root. Submit the repo URL after signing in to the [Mech Royale track](https://www.joinbuilders.org/buildathon/tracks/builders).
