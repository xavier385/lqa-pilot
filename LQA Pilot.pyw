"""Double-click launcher for Python installations; the packaged EXE requires no Python."""
import sys
try:
    from lqa_pilot.desktop import main
    main()
except Exception:
    if '--self-check' in sys.argv:
        import traceback
        from pathlib import Path
        Path(sys.executable).with_name('self-check-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise SystemExit(1)
    raise
