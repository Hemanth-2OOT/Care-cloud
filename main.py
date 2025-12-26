from carecloud.app import app

# Do not include the if __name__ == "__main__": app.run() block 
# when deploying to Railway with Gunicorn. 
# Gunicorn will automatically bind to the correct $PORT variable.
