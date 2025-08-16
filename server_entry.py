# ../warehouse-python/server_entry.py
import os
from app import create_app

def main():
    port = int(os.environ.get("PORT", "5077"))
    app = create_app()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
