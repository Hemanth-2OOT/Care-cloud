import os
from carecloud.app import app

if __name__ == "__main__":
    # This allows Railway to tell the app which port to use
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
    
