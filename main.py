import os
from carecloud.app import app

if __name__ == "__main__":
    # Railway will inject a PORT, but if not, it defaults to 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
    
