"""Console-only frozen entry point: stdout is Chrome framing, never GUI/logs."""
from morgan_media_downloader.youtube_companion.native_host import main

raise SystemExit(main())
