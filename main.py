import os
from carecloud.app import app

if __name__ == "__main__":
    # This MUST use os.environ.get("PORT") without a hardcoded default for Railway
    port = int(os.environ.get("PORT", 8080)) 
    app.run(host="0.0.0.0", port=port)
    
