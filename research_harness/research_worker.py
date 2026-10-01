"""Private background entry point launched only by `research start --execute`."""
import os
import sys

from .autoresearch import Campaign


def main():
    workspace, activity_id, token = sys.argv[1:]
    campaign = Campaign(workspace, activity_id)
    # Evaluators may import only their declared small task helpers from this cwd.
    os.chdir(campaign.directory / "task")
    campaign.run(token)


if __name__ == "__main__":
    main()
