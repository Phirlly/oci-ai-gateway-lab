"""Run the same deployment controller locally or in GitHub Actions."""

import sys

from .action_entrypoint import main

sys.exit(main())
