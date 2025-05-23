import sys
from app.app import MediaWikiViewerApp

def main():
    app = MediaWikiViewerApp()
    raise SystemExit(app.run(sys.argv))

if __name__ == "__main__":
    _ = main()