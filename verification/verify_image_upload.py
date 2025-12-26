import requests

def run():
    url = "http://127.0.0.1:5000/analyze"

    # 1. Login Cookie
    session = requests.Session()
    session.post("http://127.0.0.1:5000/login", data={"email": "test@test.com", "password": "pw"})

    # 2. Test Image Upload (Empty Text)
    # Create a dummy image
    from PIL import Image
    import io
    img = Image.new('RGB', (100, 100), color = 'red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    files = {'image': ('test.png', img_byte_arr, 'image/png')}
    data = {'text': ''}

    try:
        r = session.post(url, data=data, files=files)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text[:200]}")

        if r.status_code == 200:
             print("Image upload test passed (fallback to local likely)")
        else:
             print("Image upload test failed")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run()
